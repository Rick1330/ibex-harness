package http

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/mockllm"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
)

const chatOverheadBody = `{"model":"gpt-4o","messages":[{"role":"user","content":"ping"}]}`
const chatOverheadToken = "bench-chat-overhead-token"

// BenchmarkProxyChatOverhead measures POST /v1/chat/completions through the full
// middleware chain with a warmed auth LRU, Redis rate limit, warmed directive
// cache, and an immediate mockllm provider (ADR-0034).
func BenchmarkProxyChatOverhead(b *testing.B) {
	runChatOverheadBench(b, false)
}

// BenchmarkProxyChatOverheadParallel is complementary to k6's 100-VU gate.
func BenchmarkProxyChatOverheadParallel(b *testing.B) {
	runChatOverheadBench(b, true)
}

func runChatOverheadBench(b *testing.B, parallel bool) {
	handler, body := warmChatOverhead(b)
	b.ReportAllocs()
	b.ResetTimer()
	if parallel {
		runChatOverheadParallel(b, handler, body)
		return
	}
	for i := 0; i < b.N; i++ {
		if code := chatOverheadStatus(handler, body); code != http.StatusOK {
			b.Fatalf("status=%d", code)
		}
	}
}

func runChatOverheadParallel(b *testing.B, handler http.Handler, body []byte) {
	b.Helper()
	errCh := make(chan int, 1)
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			if code := chatOverheadStatus(handler, body); code != http.StatusOK {
				select {
				case errCh <- code:
				default:
				}
				return
			}
		}
	})
	select {
	case code := <-errCh:
		b.Fatalf("status=%d", code)
	default:
	}
}

func warmChatOverhead(b *testing.B) (http.Handler, []byte) {
	b.Helper()
	handler := newChatOverheadHandler(b)
	body := []byte(chatOverheadBody)
	if code := chatOverheadStatus(handler, body); code != http.StatusOK {
		b.Fatalf("setup status=%d", code)
	}
	return handler, body
}

func chatOverheadStatus(handler http.Handler, body []byte) int {
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, newChatOverheadRequest(body))
	return rec.Code
}

func newChatOverheadRequest(body []byte) *http.Request {
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+chatOverheadToken)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", testChatAgentID)
	return req
}

func newChatOverheadHandler(b *testing.B) http.Handler {
	b.Helper()
	orgUUID := uuid.MustParse(testChatOrgID)
	agentUUID := uuid.MustParse(testChatAgentID)
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), mockllm.Provider{})
	if err != nil {
		b.Fatalf("registry: %v", err)
	}
	return mustNewRouter(b, RouterDeps{
		Config:            chatTestConfig(),
		Logger:            logger.Discard("proxy"),
		Metrics:           metrics.NewProxy("chat-overhead"),
		Tracer:            telemetry.NoopTracer("proxy"),
		Validator:         newWarmedChatValidator(b, orgUUID),
		AgentVerifier:     passAgentVerifier{},
		Limiter:           newBenchRedisLimiter(b),
		DirectiveResolver: newWarmedBenchDirective(b, orgUUID, agentUUID),
		Health:            testHealthServer(),
		ProviderRegistry:  reg,
	})
}

func newWarmedChatValidator(b *testing.B, orgUUID uuid.UUID) auth.TokenValidator {
	b.Helper()
	inner := &chatMockValidator{res: &auth.ValidateResult{
		OrgID: orgUUID, Permissions: permissions.ProxyChatCompletion,
	}}
	wrapped, err := auth.WrapWithCache(inner, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err != nil {
		b.Fatalf("WrapWithCache: %v", err)
	}
	if _, err := wrapped.Validate(context.Background(), chatOverheadToken); err != nil {
		b.Fatalf("auth warm: %v", err)
	}
	return wrapped
}

func newBenchRedisLimiter(b *testing.B) ratelimit.Limiter {
	b.Helper()
	mr := miniredis.RunT(b)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	b.Cleanup(func() { _ = client.Close() })
	limiter, err := ratelimit.NewRedisSlider(client, ratelimit.RedisSliderConfig{DefaultRPM: 1_000_000})
	if err != nil {
		b.Fatalf("NewRedisSlider: %v", err)
	}
	return limiter
}

type benchDirectiveLoader struct {
	value directive.Resolved
}

func (l benchDirectiveLoader) Load(context.Context, uuid.UUID, uuid.UUID) (directive.Resolved, error) {
	return l.value, nil
}

func newWarmedBenchDirective(b *testing.B, orgID, agentID uuid.UUID) directive.Resolver {
	b.Helper()
	mr := miniredis.RunT(b)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	b.Cleanup(func() { _ = client.Close() })
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client,
		Loader: benchDirectiveLoader{value: directive.Resolved{
			Content: "bench directive", InjectionMode: "system_first",
		}},
		Config: directive.Config{CacheTTL: time.Minute},
		Log:    logger.Discard("directive"),
	})
	if err != nil {
		b.Fatalf("CachedResolver: %v", err)
	}
	if _, err := r.Resolve(context.Background(), orgID, agentID); err != nil {
		b.Fatalf("directive warm: %v", err)
	}
	waitBenchDirectiveKey(b, client, orgID, agentID)
	return r
}

func waitBenchDirectiveKey(b *testing.B, client *redis.Client, orgID, agentID uuid.UUID) {
	b.Helper()
	key := directive.CacheKey(orgID, agentID)
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if client.Exists(context.Background(), key).Val() == 1 {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	b.Fatal("timeout waiting for directive redis key")
}
