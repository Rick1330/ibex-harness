package modelpolicy

import (
	"context"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
)

type epochBumpLoader struct {
	epoch atomic.Uint64
}

func (l *epochBumpLoader) LoadOrg(_ context.Context, _ uuid.UUID) (OrgPolicies, error) {
	return OrgPolicies{Epoch: l.epoch.Load(), Policies: []Policy{}}, nil
}

func TestEpochPoller_InvalidatesOnEpochDrift(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &epochBumpLoader{}
	loader.epoch.Store(1)
	cache, err := NewCache(loader, Config{CacheTTL: time.Hour, LRUSize: 8, LoadTimeout: time.Second}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if _, ok := cache.CachedEpoch(org); !ok {
		t.Fatal("expected cached epoch after load")
	}
	loader.epoch.Store(2)
	poller := NewEpochPoller(loader, cache, logger.Discard("t"), time.Hour)
	poller.pollOnce(context.Background())
	if _, ok := cache.CachedEpoch(org); ok {
		t.Fatal("expected invalidation after epoch drift")
	}
}

func TestEpochPoller_LoadTimeoutInvalidatesAndContinues(t *testing.T) {
	t.Parallel()
	orgA, orgB := uuid.New(), uuid.New()
	slow := &blockingLoader{block: make(chan struct{})}
	cache, err := NewCache(slow, Config{CacheTTL: time.Hour, LRUSize: 8, LoadTimeout: 20 * time.Millisecond}, nil)
	if err != nil {
		t.Fatal(err)
	}
	// Seed gens/LRU via direct install of fake entries through PoliciesForOrg with a fast loader swap.
	fast := &staticEpochLoader{epoch: 1}
	cache.loader = fast
	if _, err := cache.PoliciesForOrg(context.Background(), orgA); err != nil {
		t.Fatal(err)
	}
	if _, err := cache.PoliciesForOrg(context.Background(), orgB); err != nil {
		t.Fatal(err)
	}
	cache.loader = slow
	poller := NewEpochPoller(slow, cache, logger.Discard("t"), time.Hour)
	done := make(chan struct{})
	go func() {
		poller.pollOnce(context.Background())
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		close(slow.block)
		t.Fatal("pollOnce hung on load timeout")
	}
	close(slow.block)
	// Both orgs must be fail-closed invalidated so the next request reloads;
	// polling must continue after the first organization times out.
	if _, ok := cache.CachedEpoch(orgA); ok {
		t.Fatal("expected orgA invalidated after load timeout")
	}
	if _, ok := cache.CachedEpoch(orgB); ok {
		t.Fatal("expected orgB invalidated after load timeout")
	}
}

type staticEpochLoader struct{ epoch uint64 }

func (s *staticEpochLoader) LoadOrg(_ context.Context, _ uuid.UUID) (OrgPolicies, error) {
	return OrgPolicies{Epoch: s.epoch, Policies: []Policy{}}, nil
}

type blockingLoader struct{ block chan struct{} }

func (b *blockingLoader) LoadOrg(ctx context.Context, _ uuid.UUID) (OrgPolicies, error) {
	select {
	case <-ctx.Done():
		return OrgPolicies{}, ctx.Err()
	case <-b.block:
		return OrgPolicies{Epoch: 1, Policies: []Policy{}}, nil
	}
}
