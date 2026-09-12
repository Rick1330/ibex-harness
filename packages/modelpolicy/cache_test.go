package modelpolicy

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

type fakeLoader struct {
	policies map[uuid.UUID][]Policy
	calls    int
	err      error
	mu       sync.Mutex
}

func (f *fakeLoader) LoadOrg(_ context.Context, orgID uuid.UUID) ([]Policy, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return append([]Policy(nil), f.policies[orgID]...), nil
}

func (f *fakeLoader) callCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls
}

type fakeProvider struct{ models []string }

func (f fakeProvider) Name() string              { return "test" }
func (f fakeProvider) SupportedModels() []string { return f.models }
func (f fakeProvider) Complete(context.Context, provider.Request) (provider.Response, error) {
	return provider.Response{}, errors.New("unused")
}

func testCatalog(models ...string) provider.CapabilityCatalog {
	cat := provider.CapabilityCatalog{}
	for _, m := range models {
		cat[m] = provider.ModelCapability{
			ModelID: m, Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 128000, MaxOutputTokens: 4096,
			SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyO200kBase,
		}
	}
	return cat
}

func TestCache_LRUHitAndInvalidate(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{
		org: {{Pattern: "claude-*", Allowed: false, Priority: 1}},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 16}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 1 {
		t.Fatalf("calls=%d want 1", loader.callCount())
	}
	cache.Invalidate(org)
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 2 {
		t.Fatalf("calls=%d want 2 after invalidate", loader.callCount())
	}
}

func TestCache_TTLExpiry(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{org: {}}}
	cache, err := NewCache(loader, Config{CacheTTL: 50 * time.Millisecond, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	cache.now = func() time.Time { return now }
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	now = now.Add(100 * time.Millisecond)
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 2 {
		t.Fatalf("calls=%d want 2 after TTL", loader.callCount())
	}
}

func TestOrgAwareRegistry_DenyAndAllow(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	const model = "claude-sonnet-4-5"
	base, err := provider.NewRegistry(testCatalog(model), fakeProvider{models: []string{model}})
	if err != nil {
		t.Fatal(err)
	}
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{
		org: {{Pattern: "claude-*", Allowed: false, Priority: 1}},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	reg, err := NewOrgAwareRegistry(base, cache, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := reg.ForOrg(context.Background(), org, model); !errors.Is(err, ErrModelNotAllowedForOrg) {
		t.Fatalf("deny err=%v", err)
	}
	loader.mu.Lock()
	loader.policies[org] = []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}}
	loader.mu.Unlock()
	cache.Invalidate(org)
	if _, err := reg.ForOrg(context.Background(), org, model); err != nil {
		t.Fatalf("allow: %v", err)
	}
	other := uuid.New()
	if _, err := reg.ForOrg(context.Background(), other, model); err != nil {
		t.Fatalf("no policy rows: %v", err)
	}
}

func TestOrgAwareRegistry_NilOrgFailClosed(t *testing.T) {
	t.Parallel()
	base, err := provider.NewRegistry(testCatalog("gpt-4o"), fakeProvider{models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatal(err)
	}
	cache, err := NewCache(&fakeLoader{policies: map[uuid.UUID][]Policy{}}, Config{LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	reg, err := NewOrgAwareRegistry(base, cache, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	_, err = reg.ForOrg(context.Background(), uuid.Nil, "gpt-4o")
	if !errors.Is(err, ErrPolicyUnavailable) {
		t.Fatalf("err=%v", err)
	}
}

func TestPassthroughRegistry(t *testing.T) {
	t.Parallel()
	p := PassthroughRegistry{}
	if _, err := p.ForOrg(context.Background(), uuid.New(), "x"); !errors.Is(err, provider.ErrNoProviderForModel) {
		t.Fatalf("err=%v", err)
	}
}

func TestEventRoundTrip(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	ev := InvalidateEvent{Version: CurrentEventVersion, OrgID: org.String()}
	b, err := ev.Marshal()
	if err != nil {
		t.Fatal(err)
	}
	got, err := ParseInvalidateEvent(string(b))
	if err != nil {
		t.Fatal(err)
	}
	if got.OrgID != org.String() {
		t.Fatalf("org=%q", got.OrgID)
	}
	ch := ChannelForOrg(org)
	parsed, err := OrgIDFromChannel(ch)
	if err != nil || parsed != org {
		t.Fatalf("channel parse %v %v", parsed, err)
	}
}

func TestParseInvalidateEvent_RejectsBad(t *testing.T) {
	t.Parallel()
	cases := []string{
		`{`,
		`{"v":2,"org_id":"550e8400-e29b-41d4-a716-446655440000"}`,
		`{"v":1,"org_id":""}`,
		`{"v":1,"org_id":"not-a-uuid"}`,
	}
	for _, raw := range cases {
		if _, err := ParseInvalidateEvent(raw); err == nil {
			t.Fatalf("expected error for %s", raw)
		}
	}
}

func TestCache_LoaderErrorFailClosed(t *testing.T) {
	t.Parallel()
	loader := &fakeLoader{err: errors.New("db down")}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	_, err = cache.PoliciesForOrg(context.Background(), uuid.New())
	if !errors.Is(err, ErrPolicyUnavailable) {
		t.Fatalf("err=%v", err)
	}
}

func TestCache_BadPatternInDBFailClosed(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{
		org: {{Pattern: "[]", Allowed: false, Priority: 1}},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	_, err = cache.PoliciesForOrg(context.Background(), org)
	if !errors.Is(err, ErrPolicyUnavailable) {
		t.Fatalf("err=%v", err)
	}
}

func TestCache_InvalidateDuringLoadRejectsStaleAndRetries(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &seqBlockingLoader{
		started: make(chan struct{}),
		release: make(chan struct{}),
		first:   []Policy{{Pattern: "claude-*", Allowed: false, Priority: 1}},
		second:  []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}},
	}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	errCh := make(chan error, 1)
	var got []Policy
	go func() {
		var loadErr error
		got, loadErr = cache.PoliciesForOrg(context.Background(), org)
		errCh <- loadErr
	}()
	<-loader.started
	cache.Invalidate(org)
	close(loader.release)
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || !got[0].Allowed {
		t.Fatalf("returned stale deny: %+v", got)
	}
	if loader.calls != 2 {
		t.Fatalf("calls=%d want 2", loader.calls)
	}
}

func TestCache_InvalidateAfterLoadBeforeInstall(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	var cache *Cache
	loader := &hookLoader{
		policies: []Policy{{Pattern: "claude-*", Allowed: false, Priority: 1}},
	}
	var err error
	cache, err = NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	loader.afterLoad = func() {
		cache.Invalidate(org)
		loader.policies = []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}}
		loader.afterLoad = nil
	}
	got, err := cache.PoliciesForOrg(context.Background(), org)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || !got[0].Allowed {
		t.Fatalf("must not stick stale deny after post-load invalidate: %+v", got)
	}
	if loader.calls < 2 {
		t.Fatalf("calls=%d want >=2", loader.calls)
	}
}

func TestCache_InvalidateEveryLoadFailsClosed(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader := &invalidateOnLoad{org: org}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	loader.cache = cache
	_, err = cache.PoliciesForOrg(context.Background(), org)
	if !errors.Is(err, ErrPolicyUnavailable) {
		t.Fatalf("err=%v want ErrPolicyUnavailable", err)
	}
	if loader.calls != maxPolicyLoadAttempts {
		t.Fatalf("calls=%d want %d", loader.calls, maxPolicyLoadAttempts)
	}
}

type seqBlockingLoader struct {
	started, release chan struct{}
	first, second    []Policy
	calls            int
}

func (s *seqBlockingLoader) LoadOrg(_ context.Context, _ uuid.UUID) ([]Policy, error) {
	s.calls++
	if s.calls == 1 {
		close(s.started)
		<-s.release
		return append([]Policy(nil), s.first...), nil
	}
	return append([]Policy(nil), s.second...), nil
}

type hookLoader struct {
	policies  []Policy
	afterLoad func()
	calls     int
}

func (h *hookLoader) LoadOrg(_ context.Context, _ uuid.UUID) ([]Policy, error) {
	h.calls++
	out := append([]Policy(nil), h.policies...)
	if h.afterLoad != nil {
		h.afterLoad()
	}
	return out, nil
}

type invalidateOnLoad struct {
	cache *Cache
	org   uuid.UUID
	calls int
}

func (i *invalidateOnLoad) LoadOrg(_ context.Context, _ uuid.UUID) ([]Policy, error) {
	i.calls++
	i.cache.Invalidate(i.org)
	return []Policy{{Pattern: "x*", Allowed: false, Priority: 1}}, nil
}

func TestCache_GensPrunedOnCapacityEviction(t *testing.T) {
	t.Parallel()
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 2}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	orgs := []uuid.UUID{uuid.New(), uuid.New(), uuid.New()}
	for _, org := range orgs {
		loader.policies[org] = []Policy{{Pattern: "a*", Allowed: true, Priority: 1}}
		if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
			t.Fatal(err)
		}
	}
	// Capacity-2 LRU: loading the third org evicts the first; gens for the
	// evicted live generation must be pruned (not retained forever).
	if n := cache.gensLen(); n > 2 {
		t.Fatalf("gensLen=%d want <=2 after capacity eviction", n)
	}
	// Invalidate must still retain a bumped generation for a key not in LRU.
	evicted := orgs[0]
	cache.Invalidate(evicted)
	if cache.gensLen() < 1 {
		t.Fatal("expected invalidate to retain generation bump")
	}
}

func TestCache_GensBoundedUnderConcurrentCapacityChurn(t *testing.T) {
	t.Parallel()
	const lruSize = 8
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: lruSize}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			org := uuid.New()
			loader.mu.Lock()
			loader.policies[org] = []Policy{{Pattern: "m*", Allowed: true, Priority: 1}}
			loader.mu.Unlock()
			_, _ = cache.PoliciesForOrg(context.Background(), org)
		}()
	}
	wg.Wait()
	// Live gens track at most the LRU population (plus brief invalidate bumps).
	if n := cache.gensLen(); n > lruSize*2 {
		t.Fatalf("gensLen=%d want <=%d under capacity churn", n, lruSize*2)
	}
}

// Gen-0 allow install must not clobber a newer deny via blind Remove on stale cleanup.
func TestCache_StaleRemovePreservesNewerInstall(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	model := "deny-me-x"
	gate0 := make(chan struct{})
	gate1 := make(chan struct{})
	installed1 := make(chan struct{})
	loader := &orderedPolicyLoader{
		org: org,
		steps: []orderedLoadStep{
			{policies: []Policy{{Pattern: "deny-me-*", Allowed: true, Priority: 1}}, wait: gate0},
			{policies: []Policy{{Pattern: "deny-me-*", Allowed: false, Priority: 1}}, wait: gate1},
		},
		started: []chan struct{}{make(chan struct{}), make(chan struct{})},
	}
	cache, err := NewCache(loader, Config{CacheTTL: time.Minute, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	base, err := provider.NewRegistry(testCatalog(model), fakeProvider{models: []string{model}})
	if err != nil {
		t.Fatal(err)
	}
	reg, err := NewOrgAwareRegistry(base, cache, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}

	err0 := make(chan error, 1)
	go func() {
		_, e := cache.PoliciesForOrg(context.Background(), org)
		err0 <- e
	}()
	<-loader.started[0]

	cache.Invalidate(org)
	err1 := make(chan error, 1)
	go func() {
		_, e := cache.PoliciesForOrg(context.Background(), org)
		close(installed1)
		err1 <- e
	}()
	<-loader.started[1]
	close(gate1)
	if err := <-err1; err != nil {
		t.Fatalf("gen1 load: %v", err)
	}
	<-installed1

	close(gate0)
	if err := <-err0; err != nil {
		t.Fatalf("gen0 load: %v", err)
	}

	_, err = reg.ForOrg(context.Background(), org, model)
	if !errors.Is(err, ErrModelNotAllowedForOrg) {
		t.Fatalf("want deny after newer install, got %v", err)
	}
}

type orderedLoadStep struct {
	policies []Policy
	wait     chan struct{}
}

type orderedPolicyLoader struct {
	org     uuid.UUID
	steps   []orderedLoadStep
	mu      sync.Mutex
	idx     int
	started []chan struct{}
}

func (o *orderedPolicyLoader) LoadOrg(_ context.Context, orgID uuid.UUID) ([]Policy, error) {
	if orgID != o.org {
		return nil, fmt.Errorf("unexpected org")
	}
	o.mu.Lock()
	i := o.idx
	o.idx++
	if i >= len(o.steps) {
		last := o.steps[len(o.steps)-1]
		o.mu.Unlock()
		return append([]Policy(nil), last.policies...), nil
	}
	if i >= len(o.started) {
		o.mu.Unlock()
		return nil, fmt.Errorf("missing started channel for step %d", i)
	}
	started := o.started[i]
	step := o.steps[i]
	o.mu.Unlock()
	close(started)
	<-step.wait
	return append([]Policy(nil), step.policies...), nil
}
