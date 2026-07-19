package gobench

// Package gobench — proxy overhead stage microbenchmarks.
//
// PLACEHOLDER NOTICE (milestone 2.6.1; tracked in
// https://github.com/Rick1330/ibex-harness/issues/291):
// stageRateLimit exercises real packages/ratelimit. Remaining stage* helpers
// are SYNTHETIC stand-ins until the packages below exist. The Phase 2 latency
// gate is green only after all stages are real.
//
// Replacement matrix (synthetic stages → real packages):
//
//	| Synthetic          | Replace with                                      | Package / path              | Status |
//	|--------------------|---------------------------------------------------|-----------------------------|--------|
//	| stageAuth          | Auth cache hit path (LRU)                         | packages/authcache (2.2.1)  | TODO   |
//	| stageRateLimit     | Limiter.Check                                     | packages/ratelimit          | DONE   |
//	| stageDirectiveResolve | Directive resolve (Redis cache hit)            | proxy directive package     | TODO   |
//	| stagePromptInject  | System-prompt / messages inject                   | proxy prompt inject (2.3.x) | TODO   |
//	| BenchmarkProxyOverhead | Compose real stages + mock provider          | services/proxy + mock       | partial|
//
// Also: CI k6 defaults to GET /health; set K6_USE_CHAT=1 for POST
// /v1/chat/completions once the Phase 2 middleware chain is complete.
// Pin baseline.json target_commit/baseline_sha only after a real 2.6.1 run.

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"

	"github.com/Rick1330/ibex-harness/packages/ratelimit"
)

var benchOrgID = uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")

func stageAuth() string {
	sum := sha256.Sum256([]byte("auth-token"))
	return hex.EncodeToString(sum[:8])
}

func stageDirectiveResolve(v int) string {
	return strings.Repeat("directive:", v%5+1)
}

func stagePromptInject(s string) string {
	return "[system]" + s + "[/system]"
}

// newTestRateLimiter starts an in-process Redis and returns a Limiter + cleanup.
func newTestRateLimiter(t testing.TB) (ratelimit.Limiter, func()) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis: %v", err)
	}
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	limiter := ratelimit.NewRedisSlider(client, ratelimit.RedisSliderConfig{DefaultRPM: 1_000_000})
	cleanup := func() {
		_ = client.Close()
		mr.Close()
	}
	return limiter, cleanup
}

func mustRateLimitCheck(b *testing.B, limiter ratelimit.Limiter, ctx context.Context) {
	b.Helper()
	if _, err := limiter.Check(ctx, benchOrgID, uuid.Nil); err != nil {
		b.Fatalf("rate limit check: %v", err)
	}
}

func BenchmarkStageAuth(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = stageAuth()
	}
}

func BenchmarkStageRateLimit(b *testing.B) {
	limiter, cleanup := newTestRateLimiter(b)
	defer cleanup()
	ctx := context.Background()

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		mustRateLimitCheck(b, limiter, ctx)
	}
}

func BenchmarkStageDirectiveResolve(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = stageDirectiveResolve(i)
	}
}

func BenchmarkStagePromptInject(b *testing.B) {
	b.ReportAllocs()
	input := stageDirectiveResolve(9)
	for i := 0; i < b.N; i++ {
		_ = stagePromptInject(input)
	}
}

func BenchmarkProxyOverhead(b *testing.B) {
	limiter, cleanup := newTestRateLimiter(b)
	defer cleanup()
	ctx := context.Background()

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = stageAuth()
		mustRateLimitCheck(b, limiter, ctx)
		_ = stagePromptInject(stageDirectiveResolve(i))
	}
}
