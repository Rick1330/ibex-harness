package modelpolicy

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
)

type countingDefaults struct {
	calls atomic.Int32
	val   AgentDefaults
	err   error
}

func (c *countingDefaults) Load(context.Context, uuid.UUID, uuid.UUID) (AgentDefaults, error) {
	c.calls.Add(1)
	if c.err != nil {
		return AgentDefaults{}, c.err
	}
	return c.val, nil
}

func TestCachingAgentDefaults_HitAndTTL(t *testing.T) {
	t.Parallel()
	inner := &countingDefaults{val: AgentDefaults{DefaultModel: "gpt-4o"}}
	cache, err := NewCachingAgentDefaults(inner, Config{
		AgentDefaultsTTL: 50 * time.Millisecond,
		AgentDefaultsLRU: 8,
		LoadTimeout:      time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	got, err := cache.Load(context.Background(), org, agent)
	if err != nil || got.DefaultModel != "gpt-4o" {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	if _, err := cache.Load(context.Background(), org, agent); err != nil {
		t.Fatal(err)
	}
	if inner.calls.Load() != 1 {
		t.Fatalf("calls=%d want 1", inner.calls.Load())
	}
	now := time.Now()
	cache.now = func() time.Time { return now.Add(100 * time.Millisecond) }
	if _, err := cache.Load(context.Background(), org, agent); err != nil {
		t.Fatal(err)
	}
	if inner.calls.Load() != 2 {
		t.Fatalf("calls=%d want 2 after TTL", inner.calls.Load())
	}
}

func TestCachingAgentDefaults_PropagatesError(t *testing.T) {
	t.Parallel()
	inner := &countingDefaults{err: errors.New("db down")}
	cache, err := NewCachingAgentDefaults(inner, Config{AgentDefaultsLRU: 4})
	if err != nil {
		t.Fatal(err)
	}
	_, err = cache.Load(context.Background(), uuid.New(), uuid.New())
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestCachingAgentDefaults_CoalescesConcurrentLoads(t *testing.T) {
	t.Parallel()
	started := make(chan struct{})
	release := make(chan struct{})
	inner := &blockingDefaults{
		started: started,
		release: release,
		val:     AgentDefaults{DefaultModel: "gpt-4o"},
	}
	cache := mustCachingAgentDefaults(t, inner)
	org, agent := uuid.New(), uuid.New()
	errCh := launchConcurrentLoads(cache, org, agent, 8)
	<-started
	close(release)
	drainLoadErrors(t, errCh, 8)
	assertInnerLoadCount(t, &inner.calls, 1)
}

// First caller's cancel must return promptly as context.Canceled while the
// detached shared load continues to serve healthy peers.
func TestCachingAgentDefaults_CancelFirstCallerStillServesPeer(t *testing.T) {
	t.Parallel()
	started := make(chan struct{})
	release := make(chan struct{})
	inner := &blockingDefaults{
		started: started,
		release: release,
		val:     AgentDefaults{DefaultModel: "gpt-4o"},
	}
	cache := mustCachingAgentDefaults(t, inner)
	org, agent := uuid.New(), uuid.New()

	ownerCtx, ownerCancel := context.WithCancel(context.Background())
	ownerErr := make(chan error, 1)
	go func() {
		_, err := cache.Load(ownerCtx, org, agent)
		ownerErr <- err
	}()
	<-started
	ownerCancel()

	select {
	case err := <-ownerErr:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("owner err=%v want context.Canceled before release", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("owner did not return context.Canceled before shared load finished")
	}

	peerErr := make(chan error, 1)
	go func() { peerErr <- loadExpectModel(cache, org, agent, "gpt-4o") }()
	close(release)
	requireNoErr(t, <-peerErr)
	assertInnerLoadCount(t, &inner.calls, 1)
}

func mustCachingAgentDefaults(t *testing.T, inner AgentDefaultLoader) *CachingAgentDefaults {
	t.Helper()
	cache, err := NewCachingAgentDefaults(inner, Config{
		AgentDefaultsTTL: time.Minute,
		AgentDefaultsLRU: 8,
		LoadTimeout:      5 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	return cache
}

func launchConcurrentLoads(cache *CachingAgentDefaults, org, agent uuid.UUID, n int) <-chan error {
	errCh := make(chan error, n)
	for i := 0; i < n; i++ {
		go func() { errCh <- loadExpectModel(cache, org, agent, "gpt-4o") }()
	}
	return errCh
}

func loadExpectModel(cache *CachingAgentDefaults, org, agent uuid.UUID, want string) error {
	got, err := cache.Load(context.Background(), org, agent)
	if err != nil {
		return err
	}
	if got.DefaultModel != want {
		return errors.New("unexpected model")
	}
	return nil
}

func drainLoadErrors(t *testing.T, errCh <-chan error, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		requireNoErr(t, <-errCh)
	}
}

func requireNoErr(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func assertInnerLoadCount(t *testing.T, calls *atomic.Int32, want int32) {
	t.Helper()
	if calls.Load() != want {
		t.Fatalf("inner loads=%d want %d (singleflight)", calls.Load(), want)
	}
}

type blockingDefaults struct {
	started, release chan struct{}
	calls            atomic.Int32
	val              AgentDefaults
	once             sync.Once
}

func (b *blockingDefaults) Load(ctx context.Context, _ uuid.UUID, _ uuid.UUID) (AgentDefaults, error) {
	b.calls.Add(1)
	b.once.Do(func() { close(b.started) })
	select {
	case <-b.release:
		return b.val, nil
	case <-ctx.Done():
		return AgentDefaults{}, ctx.Err()
	}
}

func TestNewAgentStore_NilDB(t *testing.T) {
	t.Parallel()
	if _, err := NewAgentStore(nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestNoopAgentDefaults_LoadEmpty(t *testing.T) {
	t.Parallel()
	got, err := NoopAgentDefaults{}.Load(context.Background(), uuid.New(), uuid.New())
	if err != nil || got.DefaultModel != "" {
		t.Fatalf("got=%+v err=%v", got, err)
	}
}

func TestNewCachingAgentDefaults_NilInner(t *testing.T) {
	t.Parallel()
	if _, err := NewCachingAgentDefaults(nil, Config{}); err == nil {
		t.Fatal("expected error")
	}
}
