package directive_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_ResolveHitMissEmpty(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	content := "Be concise."
	store := newFakeStore(directive.Resolved{
		Content: content, InjectionMode: "system_first", VersionID: uuid.New(),
	})
	r := mustNewResolver(t, store, time.Minute)

	first, err := r.Resolve(context.Background(), orgID, agentID)
	if err != nil {
		t.Fatalf("first resolve: %v", err)
	}
	assertResolvedContent(t, first, content)
	if store.loads != 1 {
		t.Fatalf("loads=%d want 1", store.loads)
	}

	second, err := r.Resolve(context.Background(), orgID, agentID)
	if err != nil {
		t.Fatalf("second resolve: %v", err)
	}
	assertResolvedContent(t, second, content)
	if store.loads != 1 {
		t.Fatalf("loads=%d want 1 after hit", store.loads)
	}
}

func TestUnit_ResolveNegativeCache(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{})
	r := mustNewResolver(t, store, time.Minute)

	for i := 0; i < 3; i++ {
		got, err := r.Resolve(context.Background(), orgID, agentID)
		if err != nil {
			t.Fatalf("resolve %d: %v", i, err)
		}
		if got.HasContent() {
			t.Fatal("expected empty")
		}
	}
	if store.loads != 1 {
		t.Fatalf("loads=%d want 1 (negative cache)", store.loads)
	}
}

func TestUnit_InvalidateClearsCache(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{Content: "v1", InjectionMode: "system_first"})
	r := mustNewResolver(t, store, time.Minute)

	_, _ = r.Resolve(context.Background(), orgID, agentID)
	store.set(directive.Resolved{Content: "v2", InjectionMode: "system_append"})
	r.Invalidate(context.Background(), orgID, agentID)
	got, err := r.Resolve(context.Background(), orgID, agentID)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	assertResolvedContent(t, got, "v2")
	if store.loads != 2 {
		t.Fatalf("loads=%d want 2", store.loads)
	}
}

func TestUnit_RedisErrorTreatedAsMiss(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{Content: "from-db", InjectionMode: "system_first"})
	mr, client := newTestRedis(t)
	log := mustLogger(t)
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		t.Fatalf("new: %v", err)
	}
	mr.Close()

	got, err := r.Resolve(context.Background(), orgID, agentID)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	assertResolvedContent(t, got, "from-db")
	if store.loads != 1 {
		t.Fatalf("loads=%d want 1", store.loads)
	}
}

func TestUnit_StoreErrorSurfaces(t *testing.T) {
	t.Parallel()

	store := &errStore{err: errors.New("db down")}
	r := mustNewResolver(t, store, time.Minute)
	_, err := r.Resolve(context.Background(), uuid.New(), uuid.New())
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_UpdateEventRoundTrip(t *testing.T) {
	t.Parallel()

	in := directive.UpdateEvent{
		Version: 1, OrgID: uuid.New().String(), AgentID: uuid.New().String(),
		NewVersionID: uuid.New().String(),
	}
	raw, err := in.Marshal()
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	out, err := directive.ParseUpdateEvent(string(raw))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if out.OrgID != in.OrgID || out.AgentID != in.AgentID {
		t.Fatalf("mismatch: %+v", out)
	}
}

func TestUnit_UpdateEventRejectsNonUUID(t *testing.T) {
	t.Parallel()

	err := directive.UpdateEvent{Version: 1, OrgID: "not-a-uuid", AgentID: uuid.New().String()}.Validate()
	if err == nil {
		t.Fatal("expected org_id uuid error")
	}
	err = directive.UpdateEvent{Version: 1, OrgID: uuid.New().String(), AgentID: "bad"}.Validate()
	if err == nil {
		t.Fatal("expected agent_id uuid error")
	}
}

func TestUnit_NoopResolver(t *testing.T) {
	t.Parallel()

	var n directive.NoopResolver
	got, err := n.Resolve(context.Background(), uuid.New(), uuid.New())
	if err != nil || got.HasContent() {
		t.Fatalf("noop: got=%+v err=%v", got, err)
	}
	n.Invalidate(context.Background(), uuid.New(), uuid.New())
}

func TestUnit_NewCachedResolverValidation(t *testing.T) {
	t.Parallel()

	_, client := newTestRedis(t)
	log := mustLogger(t)
	store := newFakeStore(directive.Resolved{})
	if _, err := directive.NewCachedResolver(directive.CachedResolverDeps{}); err == nil {
		t.Fatal("expected error for empty deps")
	}
	if _, err := directive.NewCachedResolver(directive.CachedResolverDeps{Client: client}); err == nil {
		t.Fatal("expected store required")
	}
	if _, err := directive.NewCachedResolver(directive.CachedResolverDeps{Client: client, Loader: store}); err == nil {
		t.Fatal("expected logger required")
	}
	if _, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Log: log,
	}); err != nil {
		t.Fatalf("valid deps: %v", err)
	}
}

func TestUnit_PubSubInvalidate(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{Content: "cached", InjectionMode: "system_first"})
	mr, client := newTestRedis(t)
	log := mustLogger(t)
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	_, _ = r.Resolve(context.Background(), orgID, agentID)
	if store.loads != 1 {
		t.Fatalf("loads=%d", store.loads)
	}

	sub, err := directive.NewSubscriber(client, r, log, nil)
	if err != nil {
		t.Fatalf("subscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)
	waitSubscribed(t, mr)

	pub, err := directive.NewRedisPublisher(client, log)
	if err != nil {
		t.Fatalf("publisher: %v", err)
	}
	store.set(directive.Resolved{Content: "fresh", InjectionMode: "system_first"})
	if err := pub.Publish(ctx, directive.UpdateEvent{
		Version: 1, OrgID: orgID.String(), AgentID: agentID.String(),
	}); err != nil {
		t.Fatalf("publish: %v", err)
	}
	waitUntil(t, 2*time.Second, func() bool {
		got, err := r.Resolve(context.Background(), orgID, agentID)
		return err == nil && got.Content == "fresh" && store.loads >= 2
	})
	sub.Stop()
	cancel()
	<-sub.Done()
}

func TestUnit_EnvelopeRoundTrip(t *testing.T) {
	t.Parallel()

	orgID := uuid.New()
	agentID := uuid.New()
	versionID := uuid.New()
	store := newFakeStore(directive.Resolved{
		Content: "x", InjectionMode: "system_append", VersionID: versionID,
	})
	r := mustNewResolver(t, store, time.Minute)
	got, err := r.Resolve(context.Background(), orgID, agentID)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if got.VersionID != versionID || got.InjectionMode != "system_append" {
		t.Fatalf("envelope: %+v", got)
	}
	hit, err := r.Resolve(context.Background(), orgID, agentID)
	if err != nil || hit.VersionID != versionID {
		t.Fatalf("cache hit: %+v err=%v", hit, err)
	}
}

func TestUnit_ConfigApplyDefaults(t *testing.T) {
	t.Parallel()

	var cfg directive.Config
	cfg.ApplyDefaults()
	if cfg.CacheTTL != 60*time.Second {
		t.Fatalf("ttl=%v", cfg.CacheTTL)
	}
}

func BenchmarkCachedResolver_ResolveHit(b *testing.B) {
	orgID := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	agentID := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	store := newFakeStore(directive.Resolved{Content: "bench", InjectionMode: "system_first"})
	mr := miniredis.RunT(b)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	b.Cleanup(func() { _ = client.Close() })
	log, err := logger.New(logger.Config{Service: "directive-bench"})
	if err != nil {
		b.Fatal(err)
	}
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		b.Fatal(err)
	}
	if _, err := r.Resolve(context.Background(), orgID, agentID); err != nil {
		b.Fatal(err)
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := r.Resolve(context.Background(), orgID, agentID); err != nil {
			b.Fatal(err)
		}
	}
}

type fakeStore struct {
	mu    sync.Mutex
	value directive.Resolved
	loads int
	err   error
}

func newFakeStore(v directive.Resolved) *fakeStore {
	return &fakeStore{value: v}
}

func (s *fakeStore) set(v directive.Resolved) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.value = v
}

func (s *fakeStore) Load(context.Context, uuid.UUID, uuid.UUID) (directive.Resolved, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.loads++
	if s.err != nil {
		return directive.Resolved{}, s.err
	}
	return s.value, nil
}

type errStore struct{ err error }

func (s *errStore) Load(context.Context, uuid.UUID, uuid.UUID) (directive.Resolved, error) {
	return directive.Resolved{}, s.err
}

func mustNewResolver(t *testing.T, store directive.Loader, ttl time.Duration) *directive.CachedResolver {
	t.Helper()
	_, client := newTestRedis(t)
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: ttl}, Log: mustLogger(t),
	})
	if err != nil {
		t.Fatalf("NewCachedResolver: %v", err)
	}
	return r
}

func newTestRedis(t *testing.T) (*miniredis.Miniredis, *redis.Client) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return mr, client
}

func mustLogger(t *testing.T) *logger.Logger {
	t.Helper()
	log, err := logger.New(logger.Config{Service: "directive-test"})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	return log
}

func assertResolvedContent(t *testing.T, got directive.Resolved, want string) {
	t.Helper()
	if got.Content != want {
		t.Fatalf("content=%q want %q", got.Content, want)
	}
}

func waitSubscribed(t *testing.T, mr *miniredis.Miniredis) {
	t.Helper()
	waitUntil(t, 2*time.Second, func() bool {
		return mr.PubSubNumPat() > 0
	})
}

func waitUntil(t *testing.T, d time.Duration, ok func() bool) {
	t.Helper()
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		if ok() {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("timeout waiting for condition")
}
