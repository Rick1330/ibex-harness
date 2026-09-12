package modelpolicy

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

type fakeLoader struct {
	policies map[uuid.UUID][]Policy
	calls    int
	err      error
}

func (f *fakeLoader) LoadOrg(_ context.Context, orgID uuid.UUID) ([]Policy, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return append([]Policy(nil), f.policies[orgID]...), nil
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
	if loader.calls != 1 {
		t.Fatalf("calls=%d want 1", loader.calls)
	}
	cache.Invalidate(org)
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.calls != 2 {
		t.Fatalf("calls=%d want 2 after invalidate", loader.calls)
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
	if loader.calls != 2 {
		t.Fatalf("calls=%d want 2 after TTL", loader.calls)
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
	loader.policies[org] = []Policy{{Pattern: "claude-*", Allowed: true, Priority: 1}}
	cache.Invalidate(org)
	if _, err := reg.ForOrg(context.Background(), org, model); err != nil {
		t.Fatalf("allow: %v", err)
	}
	other := uuid.New()
	if _, err := reg.ForOrg(context.Background(), other, model); err != nil {
		t.Fatalf("no policy rows: %v", err)
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

func TestCache_InvalidateDuringLoadRejectsStaleAndRetries(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	loader, cache := newInvalidateRetryFixture(t)
	got := loadPoliciesWhileInvalidating(t, cache, org, loader.started, loader.release)
	assertSingleAllowPolicy(t, got)
	assertCachedAllowPolicy(t, cache, org)
	if loader.calls != 2 {
		t.Fatalf("calls=%d want 2 (retry after invalidate)", loader.calls)
	}
}

func newInvalidateRetryFixture(t *testing.T) (*seqBlockingLoader, *Cache) {
	t.Helper()
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
	return loader, cache
}

func loadPoliciesWhileInvalidating(
	t *testing.T, cache *Cache, org uuid.UUID, started, release chan struct{},
) []Policy {
	t.Helper()
	errCh := make(chan error, 1)
	var got []Policy
	go func() {
		var loadErr error
		got, loadErr = cache.PoliciesForOrg(context.Background(), org)
		errCh <- loadErr
	}()
	<-started
	cache.Invalidate(org)
	close(release)
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	return got
}

func assertSingleAllowPolicy(t *testing.T, got []Policy) {
	t.Helper()
	if len(got) != 1 || !got[0].Allowed {
		t.Fatalf("returned stale deny snapshot: %+v", got)
	}
}

func assertCachedAllowPolicy(t *testing.T, cache *Cache, org uuid.UUID) {
	t.Helper()
	cached, ok := cache.lookupFresh(org.String())
	if !ok || len(cached) != 1 || !cached[0].Allowed {
		t.Fatalf("LRU must hold fresh allow policies: ok=%v cached=%+v", ok, cached)
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
