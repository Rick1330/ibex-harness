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

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		metrics.mu.Lock()
		ok := metrics.runs["ok"] > 0
		metrics.mu.Unlock()
		if ok {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}

	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	if metrics.runs["ok"] < 1 || metrics.marked < 1 {
		t.Fatalf("metrics=%+v", metrics)
	}
	if _, hit := cache.Get(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}); hit {
		t.Fatal("expected cache invalidate")
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	wantCutoff := fixed.Add(-time.Hour)
	if !store.lastIdle.Equal(wantCutoff) {
		t.Fatalf("idleBefore=%s want %s", store.lastIdle, wantCutoff)
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
			sw, err := sessionsweeper.New(sessionsweeper.Config{
				IdleTimeout: time.Hour, Interval: time.Hour,
			}, sessionsweeper.Deps{Store: store, Metrics: metrics})
			if err != nil {
				t.Fatal(err)
			}
			sw.Start()
			t.Cleanup(func() { _ = sw.Stop(context.Background()) })

			deadline := time.Now().Add(2 * time.Second)
			for time.Now().Before(deadline) {
				metrics.mu.Lock()
				n := metrics.runs[tc.want]
				metrics.mu.Unlock()
				if n > 0 {
					return
				}
				time.Sleep(5 * time.Millisecond)
			}
			t.Fatalf("want run result %s", tc.want)
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
