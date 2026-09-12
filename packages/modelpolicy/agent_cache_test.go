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
	cache, err := NewCachingAgentDefaults(inner, Config{
		AgentDefaultsTTL: time.Minute,
		AgentDefaultsLRU: 8,
		LoadTimeout:      5 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	const n = 8
	errCh := make(chan error, n)
	for i := 0; i < n; i++ {
		go func() {
			got, loadErr := cache.Load(context.Background(), org, agent)
			if loadErr != nil {
				errCh <- loadErr
				return
			}
			if got.DefaultModel != "gpt-4o" {
				errCh <- errors.New("unexpected model")
				return
			}
			errCh <- nil
		}()
	}
	<-started
	close(release)
	for i := 0; i < n; i++ {
		if err := <-errCh; err != nil {
			t.Fatal(err)
		}
	}
	if inner.calls.Load() != 1 {
		t.Fatalf("inner loads=%d want 1 (singleflight)", inner.calls.Load())
	}
}

type blockingDefaults struct {
	started, release chan struct{}
	calls            atomic.Int32
	val              AgentDefaults
	once             sync.Once
}

func (b *blockingDefaults) Load(context.Context, uuid.UUID, uuid.UUID) (AgentDefaults, error) {
	b.calls.Add(1)
	b.once.Do(func() { close(b.started) })
	<-b.release
	return b.val, nil
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
