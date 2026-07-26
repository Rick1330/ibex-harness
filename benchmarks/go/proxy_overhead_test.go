package gobench

// Package gobench — proxy overhead stage microbenchmarks (milestone 2.6.1).
//
// All stage* helpers call real packages on the warm path (authcache LRU hit,
// ratelimit Check, directive Redis hit, injection.Inject). See ADR-0034.
//
// Replacement matrix:
//
//	| Stage                  | Implementation                         | Status |
//	|------------------------|----------------------------------------|--------|
//	| stageAuth              | authcache.CachingValidator LRU hit     | DONE   |
//	| stageRateLimit         | ratelimit.Limiter.Check                | DONE   |
//	| stageDirectiveResolve  | directive.CachedResolver Redis hit     | DONE   |
//	| stagePromptInject      | injection.Inject                       | DONE   |
//	| BenchmarkProxyOverhead | compose four warm stages               | DONE   |
//
// Full HTTP chain: services/proxy/internal/http BenchmarkProxyChatOverhead.
// k6 full profile: K6_USE_CHAT=1 (smoke/fast keep GET /health).

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/injection"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
)

var (
	benchOrgID   = uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	benchAgentID = uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
)

type fixedAuthUpstream struct {
	res *authcache.Result
}

func (f *fixedAuthUpstream) Validate(context.Context, string) (*authcache.Result, error) {
	return f.res, nil
}

type fixedDirectiveLoader struct {
	value directive.Resolved
}

func (f fixedDirectiveLoader) Load(context.Context, uuid.UUID, uuid.UUID) (directive.Resolved, error) {
	return f.value, nil
}

type warmStages struct {
	auth      *authcache.CachingValidator
	token     string
	limiter   ratelimit.Limiter
	resolver  *directive.CachedResolver
	orgID     uuid.UUID
	agentID   uuid.UUID
	messages  []provider.Message
	directive string
}

func newWarmStages(tb testing.TB) *warmStages {
	tb.Helper()
	token := "bench-warm-token"
	up := &fixedAuthUpstream{res: &authcache.Result{OrgID: benchOrgID.String(), Permissions: 1}}
	authV, err := authcache.New(up, authcache.Config{}, logger.Discard("bench"), authcache.NoopMetrics{})
	if err != nil {
		tb.Fatalf("authcache: %v", err)
	}
	if _, err := authV.Validate(context.Background(), token); err != nil {
		tb.Fatalf("auth warm: %v", err)
	}

	limiter := newTestRateLimiter(tb)

	resolver, orgID, agentID := newWarmDirectiveResolver(tb)
	msgs := []provider.Message{
		{Role: "system", Content: "You are helpful."},
		{Role: "user", Content: "ping"},
	}
	return &warmStages{
		auth: authV, token: token, limiter: limiter, resolver: resolver,
		orgID: orgID, agentID: agentID, messages: msgs, directive: "Be concise.",
	}
}

func newTestRateLimiter(tb testing.TB) ratelimit.Limiter {
	tb.Helper()
	mr := miniredis.RunT(tb)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	tb.Cleanup(func() { _ = client.Close() })
	return ratelimit.NewRedisSlider(client, ratelimit.RedisSliderConfig{DefaultRPM: 1_000_000})
}

func newWarmDirectiveResolver(tb testing.TB) (*directive.CachedResolver, uuid.UUID, uuid.UUID) {
	tb.Helper()
	orgID, agentID := benchOrgID, benchAgentID
	loader := fixedDirectiveLoader{value: directive.Resolved{
		Content: "bench-directive", InjectionMode: "system_first",
	}}
	mr := miniredis.RunT(tb)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	tb.Cleanup(func() { _ = client.Close() })
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: loader,
		Config: directive.Config{CacheTTL: time.Minute},
		Log:    logger.Discard("directive-bench"),
	})
	if err != nil {
		tb.Fatalf("CachedResolver: %v", err)
	}
	if _, err := r.Resolve(context.Background(), orgID, agentID); err != nil {
		tb.Fatalf("directive warm: %v", err)
	}
	waitRedisDirective(tb, client, orgID, agentID)
	return r, orgID, agentID
}

func waitRedisDirective(tb testing.TB, client *redis.Client, orgID, agentID uuid.UUID) {
	tb.Helper()
	key := directive.CacheKey(orgID, agentID)
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if client.Exists(context.Background(), key).Val() == 1 {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	tb.Fatal("timeout waiting for directive redis key")
}

func mustStageAuth(b *testing.B, s *warmStages) {
	b.Helper()
	if _, err := s.auth.Validate(context.Background(), s.token); err != nil {
		b.Fatal(err)
	}
}

func mustStageRateLimit(b *testing.B, s *warmStages) {
	b.Helper()
	if _, err := s.limiter.Check(context.Background(), s.orgID, uuid.Nil); err != nil {
		b.Fatal(err)
	}
}

func mustStageDirective(b *testing.B, s *warmStages) directive.Resolved {
	b.Helper()
	resolved, err := s.resolver.Resolve(context.Background(), s.orgID, s.agentID)
	if err != nil {
		b.Fatal(err)
	}
	return resolved
}

func stagePromptInject(s *warmStages) []provider.Message {
	return injection.Inject(s.messages, s.directive, injection.ModeSystemFirst)
}

func mustRateLimitCheck(b *testing.B, limiter ratelimit.Limiter, ctx context.Context) {
	b.Helper()
	if _, err := limiter.Check(ctx, benchOrgID, uuid.Nil); err != nil {
		b.Fatalf("rate limit check: %v", err)
	}
}

func BenchmarkStageAuth(b *testing.B) {
	s := newWarmStages(b)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		mustStageAuth(b, s)
	}
}

func BenchmarkStageRateLimit(b *testing.B) {
	limiter := newTestRateLimiter(b)
	ctx := context.Background()
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		mustRateLimitCheck(b, limiter, ctx)
	}
}

func BenchmarkStageDirectiveResolve(b *testing.B) {
	s := newWarmStages(b)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = mustStageDirective(b, s)
	}
}

func BenchmarkStagePromptInject(b *testing.B) {
	s := newWarmStages(b)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = stagePromptInject(s)
	}
}

func BenchmarkProxyOverhead(b *testing.B) {
	s := newWarmStages(b)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		mustStageAuth(b, s)
		mustStageRateLimit(b, s)
		_ = mustStageDirective(b, s)
		_ = stagePromptInject(s)
	}
}
