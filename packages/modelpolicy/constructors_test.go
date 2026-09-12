package modelpolicy

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

func TestNewCache_NilLoader(t *testing.T) {
	t.Parallel()
	if _, err := NewCache(nil, Config{}, NoopMetrics{}); err == nil {
		t.Fatal("expected error")
	}
}

func TestNewOrgAwareRegistry_RequiresDeps(t *testing.T) {
	t.Parallel()
	base, err := provider.NewRegistry(testCatalog("gpt-4o"), fakeProvider{models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatal(err)
	}
	cache, err := NewCache(&fakeLoader{policies: map[uuid.UUID][]Policy{}}, Config{LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	t.Run("nil_base", func(t *testing.T) {
		t.Parallel()
		if _, err := NewOrgAwareRegistry(nil, cache, NoopMetrics{}); err == nil {
			t.Fatal("expected nil base error")
		}
	})
	t.Run("nil_cache", func(t *testing.T) {
		t.Parallel()
		if _, err := NewOrgAwareRegistry(base, nil, NoopMetrics{}); err == nil {
			t.Fatal("expected nil cache error")
		}
	})
}

func TestNewSubscriber_RequiresDeps(t *testing.T) {
	t.Parallel()
	if _, err := NewSubscriber(nil, nil, nil, nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestInvalidate_NilOrgNoop(t *testing.T) {
	t.Parallel()
	cache, err := NewCache(&fakeLoader{policies: map[uuid.UUID][]Policy{}}, Config{LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	cache.Invalidate(uuid.Nil)
}

func TestOrgAwareRegistry_BaseAndPassthrough(t *testing.T) {
	t.Parallel()
	base, err := provider.NewRegistry(testCatalog("gpt-4o"), fakeProvider{models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatal(err)
	}
	cache, err := NewCache(&fakeLoader{policies: map[uuid.UUID][]Policy{}}, Config{LRUSize: 4}, nil)
	if err != nil {
		t.Fatal(err)
	}
	reg, err := NewOrgAwareRegistry(base, cache, nil)
	if err != nil {
		t.Fatal(err)
	}
	if reg.Base() != base {
		t.Fatal("Base mismatch")
	}
	p := PassthroughRegistry{Base: base}
	if _, err := p.ForOrg(context.Background(), uuid.New(), "gpt-4o"); err != nil {
		t.Fatal(err)
	}
}

func TestNewStore_NilDB(t *testing.T) {
	t.Parallel()
	if _, err := NewStore(nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestCache_LookupStaleGeneration(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{
		org: {{Pattern: "claude-*", Allowed: true, Priority: 1}},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Hour, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	cache.mu.Lock()
	cache.gens[org.String()]++
	cache.mu.Unlock()
	if _, ok := cache.lookupFresh(org.String()); ok {
		t.Fatal("stale gen must miss")
	}
}
