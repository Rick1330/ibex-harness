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

func newTestCache(t *testing.T, loader BudgetLoader, lruSize int) *Cache {
	t.Helper()
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: lruSize}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	return cache
}

func hardCapSnap(capCents, spentCents int64) BudgetSnapshot {
	return BudgetSnapshot{
		HasHardCap: true, CapCents: capCents, SpentCents: spentCents, EnforcementMode: EnforcementHardCap,
	}
}

func priceCard(version string, inCents, outCents int64) CardVersion {
	return CardVersion{
		Version: version,
		Prices: []PriceRow{{
			Provider: "openai", ModelPattern: "*",
			InputCentsPer1k: inCents, OutputCentsPer1k: outCents,
		}},
	}
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
		org: hardCapSnap(100, 100),
	}}
	cache := newTestCache(t, loader, 8)
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
	cache := newTestCache(t, loader, 4)
	allowed, _, err := cache.Check(context.Background(), org)
	if err != nil || !allowed {
		t.Fatalf("allowed=%v err=%v", allowed, err)
	}
}

func TestCache_LoaderErrorFailClosed(t *testing.T) {
	t.Parallel()
	loader := &fakeBudgetLoader{err: errors.New("db down")}
	cache := newTestCache(t, loader, 4)
	_, _, err := cache.Check(context.Background(), uuid.New())
	if !errors.Is(err, ErrBudgetUnavailable) {
		t.Fatalf("err=%v", err)
	}
}

func TestCache_LRUHitAndInvalidate(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{
		org: hardCapSnap(1000, 10),
	}}
	cache := newTestCache(t, loader, 16)
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
	_, _, err := EstimateCost(priceCard("1", 100, 100), TokenUsage{
		Provider: "openai", Model: "x", InputTokens: -1, OutputTokens: 0,
	})
	if err == nil {
		t.Fatal("expected negative token error")
	}
}

func TestEstimateCost_Overflow(t *testing.T) {
	t.Parallel()
	_, _, err := EstimateCost(priceCard("1", math.MaxInt64, 1), TokenUsage{
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
			orgA: hardCapSnap(100, 0),
			orgB: hardCapSnap(100, 0),
			orgC: hardCapSnap(100, 0),
		},
		blockOn:    orgA,
		block:      block,
		release:    release,
		callsByOrg: make(map[uuid.UUID]int),
	}
	cache := newTestCache(t, loader, 2)
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
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	loader.mu.Lock()
	orgALoads := loader.callsByOrg[orgA]
	loader.mu.Unlock()
	if orgALoads < 2 {
		t.Fatalf("expected orgA loaded twice after Invalidate (stale load rejected); got %d", orgALoads)
	}
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
	snaps      map[uuid.UUID]BudgetSnapshot
	blockOn    uuid.UUID
	block      chan struct{}
	release    chan struct{}
	mu         sync.Mutex
	calls      int
	callsByOrg map[uuid.UUID]int
}

func (f *blockingBudgetLoader) LoadOrg(_ context.Context, orgID uuid.UUID) (BudgetSnapshot, error) {
	f.mu.Lock()
	f.calls++
	if f.callsByOrg == nil {
		f.callsByOrg = make(map[uuid.UUID]int)
	}
	f.callsByOrg[orgID]++
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

func TestCache_PublishedCard(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	card := CardVersion{Version: "3", Prices: []PriceRow{{Provider: "openai", ModelPattern: "*", InputCentsPer1k: 1, OutputCentsPer1k: 2}}}
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{
		org: {HasHardCap: true, CapCents: 100, SpentCents: 0, EnforcementMode: EnforcementHardCap, PublishedCard: card},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	got, err := cache.PublishedCard(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if got.Version != "3" || len(got.Prices) != 1 {
		t.Fatalf("got=%+v", got)
	}
}

func TestCache_NilOrgCheck(t *testing.T) {
	t.Parallel()
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 2}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := cache.Check(context.Background(), uuid.Nil); err == nil {
		t.Fatal("expected error for nil org")
	}
}
