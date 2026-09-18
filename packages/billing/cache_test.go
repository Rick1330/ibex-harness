package billing

import (
	"context"
	"errors"
	"math"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeBudgetLoader struct {
	snaps map[uuid.UUID]BudgetSnapshot
	calls int
	err   error
	mu    sync.Mutex
}

func (f *fakeBudgetLoader) LoadOrg(_ context.Context, orgID uuid.UUID) (BudgetSnapshot, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls++
	if f.err != nil {
		return BudgetSnapshot{}, f.err
	}
	return f.snaps[orgID], nil
}

func (f *fakeBudgetLoader) callCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls
}

func TestEstimateCost_RoundsUp(t *testing.T) {
	t.Parallel()
	card := CardVersion{
		Version: "3",
		Prices: []PriceRow{{
			Provider: "openai", ModelPattern: "gpt-4o*",
			InputCentsPer1k: 250, OutputCentsPer1k: 1000,
		}},
	}
	cents, ver, err := EstimateCost(card, TokenUsage{
		Provider: "OpenAI", Model: "gpt-4o-mini", InputTokens: 1, OutputTokens: 1,
	})
	if err != nil {
		t.Fatal(err)
	}
	if ver != "3" {
		t.Fatalf("version=%s", ver)
	}
	// ceil(1*250/1000)+ceil(1*1000/1000) = 1+1 = 2
	if cents != 2 {
		t.Fatalf("cents=%d want 2", cents)
	}
}

func TestEstimateCost_NoMatch(t *testing.T) {
	t.Parallel()
	_, _, err := EstimateCost(CardVersion{Version: "1"}, TokenUsage{Provider: "x", Model: "y"})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestCache_CheckHardCapDeny(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{
		org: {HasHardCap: true, CapCents: 100, SpentCents: 100, EnforcementMode: EnforcementHardCap},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	allowed, rem, err := cache.Check(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if allowed || rem != 0 {
		t.Fatalf("allowed=%v rem=%d", allowed, rem)
	}
}

func TestCache_CheckNoHardCapAllow(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{org: {}}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	allowed, _, err := cache.Check(context.Background(), org)
	if err != nil || !allowed {
		t.Fatalf("allowed=%v err=%v", allowed, err)
	}
}

func TestCache_LoaderErrorFailClosed(t *testing.T) {
	t.Parallel()
	loader := &fakeBudgetLoader{err: errors.New("db down")}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = cache.Check(context.Background(), uuid.New())
	if !errors.Is(err, ErrBudgetUnavailable) {
		t.Fatalf("err=%v", err)
	}
}

func TestCache_LRUHitAndInvalidate(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{
		org: {HasHardCap: true, CapCents: 1000, SpentCents: 10, EnforcementMode: EnforcementHardCap},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 16}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := cache.Check(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if _, _, err := cache.Check(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 1 {
		t.Fatalf("calls=%d want 1", loader.callCount())
	}
	cache.Invalidate(org)
	if _, _, err := cache.Check(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 2 {
		t.Fatalf("calls=%d want 2", loader.callCount())
	}
}

func TestEstimateCost_RejectsNegative(t *testing.T) {
	t.Parallel()
	card := CardVersion{
		Version: "1",
		Prices: []PriceRow{{
			Provider: "openai", ModelPattern: "*",
			InputCentsPer1k: 100, OutputCentsPer1k: 100,
		}},
	}
	_, _, err := EstimateCost(card, TokenUsage{
		Provider: "openai", Model: "x", InputTokens: -1, OutputTokens: 0,
	})
	if err == nil {
		t.Fatal("expected negative token error")
	}
}

func TestEstimateCost_Overflow(t *testing.T) {
	t.Parallel()
	card := CardVersion{
		Version: "1",
		Prices: []PriceRow{{
			Provider: "openai", ModelPattern: "*",
			InputCentsPer1k: math.MaxInt64, OutputCentsPer1k: 1,
		}},
	}
	_, _, err := EstimateCost(card, TokenUsage{
		Provider: "openai", Model: "x", InputTokens: 2, OutputTokens: 0,
	})
	if err == nil {
		t.Fatal("expected overflow error")
	}
}

func TestCache_EvictionKeepsGeneration(t *testing.T) {
	t.Parallel()
	orgA := uuid.New()
	orgB := uuid.New()
	orgC := uuid.New()
	block := make(chan struct{})
	release := make(chan struct{})
	loader := &blockingBudgetLoader{
		snaps: map[uuid.UUID]BudgetSnapshot{
			orgA: {HasHardCap: true, CapCents: 100, SpentCents: 0, EnforcementMode: EnforcementHardCap},
			orgB: {HasHardCap: true, CapCents: 100, SpentCents: 0, EnforcementMode: EnforcementHardCap},
			orgC: {HasHardCap: true, CapCents: 100, SpentCents: 0, EnforcementMode: EnforcementHardCap},
		},
		blockOn: orgA,
		block:   block,
		release: release,
	}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 2}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := cache.SnapshotForOrg(context.Background(), orgB); err != nil {
		t.Fatal(err)
	}
	if _, err := cache.SnapshotForOrg(context.Background(), orgC); err != nil {
		t.Fatal(err)
	}
	errCh := make(chan error, 1)
	go func() {
		_, e := cache.SnapshotForOrg(context.Background(), orgA)
		errCh <- e
	}()
	<-block
	cache.Invalidate(orgA)
	// Capacity eviction while A is mid-load: touch B/C then release A.
	if _, err := cache.SnapshotForOrg(context.Background(), orgB); err != nil {
		t.Fatal(err)
	}
	if _, err := cache.SnapshotForOrg(context.Background(), orgC); err != nil {
		t.Fatal(err)
	}
	close(release)
	<-errCh
	cache.mu.Lock()
	gen := cache.gens[orgA.String()]
	cache.mu.Unlock()
	if gen == 0 {
		t.Fatal("expected monotonic generation retained after invalidate/eviction")
	}
	// Evict all LRU entries and ensure gen for A still blocks zero-value install.
	orgD := uuid.New()
	loader.snaps[orgD] = BudgetSnapshot{}
	loader.blockOn = uuid.Nil
	if _, err := cache.SnapshotForOrg(context.Background(), orgD); err != nil {
		t.Fatal(err)
	}
	cache.lru.Purge()
	cache.mu.Lock()
	genAfterPurge := cache.gens[orgA.String()]
	cache.mu.Unlock()
	if genAfterPurge == 0 {
		t.Fatal("generation must survive LRU purge/eviction")
	}
}

func TestParseInvalidateEvent(t *testing.T) {
	t.Parallel()
	org := uuid.New().String()
	payload := `{"v":1,"org_id":"` + org + `"}`
	ev, err := ParseInvalidateEvent(payload)
	if err != nil {
		t.Fatal(err)
	}
	if ev.OrgID != org || ev.Version != 1 {
		t.Fatalf("%+v", ev)
	}
}

type blockingBudgetLoader struct {
	snaps   map[uuid.UUID]BudgetSnapshot
	blockOn uuid.UUID
	block   chan struct{}
	release chan struct{}
	mu      sync.Mutex
	calls   int
}

func (f *blockingBudgetLoader) LoadOrg(_ context.Context, orgID uuid.UUID) (BudgetSnapshot, error) {
	f.mu.Lock()
	f.calls++
	f.mu.Unlock()
	if orgID == f.blockOn {
		select {
		case f.block <- struct{}{}:
		default:
		}
		<-f.release
	}
	return f.snaps[orgID], nil
}
