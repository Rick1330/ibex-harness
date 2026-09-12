package modelpolicy

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

func TestConfig_ApplyDefaults(t *testing.T) {
	t.Parallel()
	var c Config
	c.ApplyDefaults()
	if c.CacheTTL != defaultCacheTTL || c.LRUSize != defaultLRUSize {
		t.Fatalf("%+v", c)
	}
	if c.AgentDefaultsTTL != defaultAgentDefaultsTTL || c.LoadTimeout != defaultLoadTimeout {
		t.Fatalf("%+v", c)
	}
}

func TestOrgIDFromChannel_RejectsBad(t *testing.T) {
	t.Parallel()
	if _, err := OrgIDFromChannel("directive_updates:x"); err == nil {
		t.Fatal("expected error")
	}
	if _, err := OrgIDFromChannel(ChannelPrefix); err == nil {
		t.Fatal("expected error")
	}
}

func TestValidatePattern_Oversize(t *testing.T) {
	t.Parallel()
	if err := ValidatePattern(string(make([]byte, 257))); err == nil {
		t.Fatal("expected oversize error")
	}
}

func TestMatch_BadPatternErrors(t *testing.T) {
	t.Parallel()
	if _, err := Match("[", "x"); err == nil {
		t.Fatal("expected match error")
	}
}

func TestEvaluatePolicies_MatchError(t *testing.T) {
	t.Parallel()
	_, err := EvaluatePolicies([]Policy{{Pattern: "[", Allowed: false, Priority: 1}}, "x")
	if err == nil {
		t.Fatal("expected error")
	}
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

func TestInvalidateEvent_MarshalRejectsBad(t *testing.T) {
	t.Parallel()
	_, err := (InvalidateEvent{Version: 99, OrgID: uuid.New().String()}).Marshal()
	if err == nil {
		t.Fatal("expected version error")
	}
}
