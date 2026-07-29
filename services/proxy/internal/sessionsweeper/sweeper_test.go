package sessionsweeper_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessionsweeper"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

type fakeStore struct {
	mu       sync.Mutex
	result   session.AbandonIdleResult
	err      error
	calls    int
	lastIdle time.Time
}

func (f *fakeStore) GetOrCreate(context.Context, session.GetOrCreateParams) (*session.Session, error) {
	return nil, errors.New("unused")
}
func (f *fakeStore) AppendCheckpoint(context.Context, session.CheckpointParams) error {
	return errors.New("unused")
}
func (f *fakeStore) Complete(context.Context, uuid.UUID, uuid.UUID) error {
	return errors.New("unused")
}
func (f *fakeStore) AbandonIdle(_ context.Context, p session.AbandonIdleParams) (session.AbandonIdleResult, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls++
	f.lastIdle = p.IdleBefore
	if f.err != nil {
		return session.AbandonIdleResult{}, f.err
	}
	return f.result, nil
}

type fakeMetrics struct {
	mu     sync.Mutex
	marked int
	runs   map[string]int
}

func (m *fakeMetrics) IncSessionSweeperMarked(string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.marked++
}

func (m *fakeMetrics) IncSessionSweeperRun(result string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.runs == nil {
		m.runs = map[string]int{}
	}
	m.runs[result]++
}

func waitForSweeperRun(t *testing.T, metrics *fakeMetrics, result string) {
	t.Helper()
	require.Eventually(t, func() bool {
		metrics.mu.Lock()
		defer metrics.mu.Unlock()
		return metrics.runs[result] > 0
	}, 2*time.Second, 5*time.Millisecond, "want run result %s", result)
}

func newTestSweeper(t *testing.T, store *fakeStore, metrics *fakeMetrics, interval time.Duration) *sessionsweeper.Sweeper {
	t.Helper()
	sw, err := sessionsweeper.New(sessionsweeper.Config{
		IdleTimeout: time.Hour, Interval: interval,
	}, sessionsweeper.Deps{Store: store, Metrics: metrics})
	if err != nil {
		t.Fatal(err)
	}
	sw.Start()
	t.Cleanup(func() { _ = sw.Stop(context.Background()) })
	return sw
}

func TestUnit_Sweeper_TickAbandonsAndInvalidates(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}

	org, agent := uuid.New(), uuid.New()
	ext := "sticky-1"
	sid := uuid.New()
	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}, sessioncache.Entry{SessionID: sid, TurnCount: 1})

	store := &fakeStore{result: session.AbandonIdleResult{
		Abandoned: []session.AbandonedSession{{
			SessionID: sid, OrgID: org, AgentID: agent, ExternalID: &ext,
		}},
	}}
	metrics := &fakeMetrics{}
	fixed := time.Date(2026, 7, 25, 12, 0, 0, 0, time.UTC)

	sw, err := sessionsweeper.New(sessionsweeper.Config{
		IdleTimeout: time.Hour, Interval: time.Minute,
	}, sessionsweeper.Deps{
		Store: store, Cache: cache, Metrics: metrics, Log: logger.Discard("proxy"),
		Now: func() time.Time { return fixed },
	})
	if err != nil {
		t.Fatal(err)
	}
	sw.Start()
	t.Cleanup(func() { _ = sw.Stop(context.Background()) })

	waitForSweeperRun(t, metrics, "ok")
	assertSweeperAbandonMetrics(t, metrics)
	assertCacheInvalidated(t, cache, sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	})
	assertSweeperIdleCutoff(t, store, fixed.Add(-time.Hour))
}

func assertSweeperAbandonMetrics(t *testing.T, metrics *fakeMetrics) {
	t.Helper()
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	if metrics.runs["ok"] < 1 || metrics.marked < 1 {
		t.Fatalf("metrics=%+v", metrics)
	}
}

func assertCacheInvalidated(t *testing.T, cache *sessioncache.Cache, key sessioncache.LookupKey) {
	t.Helper()
	if _, hit := cache.Get(context.Background(), key); hit {
		t.Fatal("expected cache invalidate")
	}
}

func assertSweeperIdleCutoff(t *testing.T, store *fakeStore, want time.Time) {
	t.Helper()
	store.mu.Lock()
	defer store.mu.Unlock()
	if !store.lastIdle.Equal(want) {
		t.Fatalf("idleBefore=%s want %s", store.lastIdle, want)
	}
}

func TestUnit_Sweeper_SkipLockAndError(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name   string
		result session.AbandonIdleResult
		err    error
		want   string
	}{
		{name: "skip", result: session.AbandonIdleResult{SkippedLock: true}, want: "skipped_lock"},
		{name: "noop", result: session.AbandonIdleResult{}, want: "noop"},
		{name: "error", err: errors.New("db down"), want: "error"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			store := &fakeStore{result: tc.result, err: tc.err}
			metrics := &fakeMetrics{}
			newTestSweeper(t, store, metrics, time.Hour)
			waitForSweeperRun(t, metrics, tc.want)
		})
	}
}

func TestUnit_Sweeper_NewValidation(t *testing.T) {
	t.Parallel()
	if _, err := sessionsweeper.New(sessionsweeper.Config{}, sessionsweeper.Deps{}); err == nil {
		t.Fatal("expected store required")
	}
	if _, err := sessionsweeper.New(sessionsweeper.Config{
		IdleTimeout: time.Second, Interval: time.Minute,
	}, sessionsweeper.Deps{Store: &fakeStore{}}); err == nil {
		t.Fatal("expected idle < interval error")
	}
}

func TestUnit_Sweeper_StopHonorsContext(t *testing.T) {
	t.Parallel()
	entered := make(chan struct{}, 1)
	release := make(chan struct{})
	store := &blockingStore{entered: entered, release: release}
	sw, err := sessionsweeper.New(sessionsweeper.Config{
		IdleTimeout: time.Hour, Interval: time.Hour,
	}, sessionsweeper.Deps{Store: store})
	if err != nil {
		t.Fatal(err)
	}
	if err := sw.Stop(context.Background()); err != nil {
		t.Fatalf("stop before start: %v", err)
	}
	sw.Start()
	sw.Start() // second start is a no-op
	select {
	case <-entered:
	case <-time.After(2 * time.Second):
		t.Fatal("tick did not enter store")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	err = sw.Stop(ctx)
	if err == nil {
		t.Fatal("expected context error while tick blocked")
	}
	close(release)
	if err := sw.Stop(context.Background()); err != nil {
		t.Fatalf("final stop: %v", err)
	}
}

type blockingStore struct {
	entered chan struct{}
	release chan struct{}
}

func (b *blockingStore) GetOrCreate(context.Context, session.GetOrCreateParams) (*session.Session, error) {
	return nil, errors.New("unused")
}
func (b *blockingStore) AppendCheckpoint(context.Context, session.CheckpointParams) error {
	return errors.New("unused")
}
func (b *blockingStore) Complete(context.Context, uuid.UUID, uuid.UUID) error {
	return errors.New("unused")
}
func (b *blockingStore) AbandonIdle(context.Context, session.AbandonIdleParams) (session.AbandonIdleResult, error) {
	select {
	case b.entered <- struct{}{}:
	default:
	}
	<-b.release
	return session.AbandonIdleResult{}, nil
}

func TestUnit_Sweeper_EmptyExternalSkipsInvalidate(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	empty := ""
	store := &fakeStore{result: session.AbandonIdleResult{
		Abandoned: []session.AbandonedSession{{
			SessionID: uuid.New(), OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: &empty,
		}},
	}}
	metrics := &fakeMetrics{}
	sw, err := sessionsweeper.New(sessionsweeper.Config{
		IdleTimeout: time.Hour, Interval: time.Hour,
	}, sessionsweeper.Deps{
		Store: store, Cache: cache, Metrics: metrics, Log: logger.Discard("proxy"),
	})
	if err != nil {
		t.Fatal(err)
	}
	sw.Start()
	t.Cleanup(func() { _ = sw.Stop(context.Background()) })
	waitForSweeperRun(t, metrics, "ok")
}

func TestUnit_Sweeper_DefaultsAndNilMetrics(t *testing.T) {
	t.Parallel()
	store := &fakeStore{result: session.AbandonIdleResult{}}
	sw, err := sessionsweeper.New(sessionsweeper.Config{}, sessionsweeper.Deps{Store: store})
	if err != nil {
		t.Fatal(err)
	}
	sw.Start()
	t.Cleanup(func() { _ = sw.Stop(context.Background()) })
	require.Eventually(t, func() bool {
		store.mu.Lock()
		defer store.mu.Unlock()
		return store.calls > 0
	}, 2*time.Second, 5*time.Millisecond, "expected tick with default interval")
}
