package metrics

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAuthHTTPMiddleware_RecordsRouteTemplate(t *testing.T) {
	t.Parallel()
	reg := NewAuth(AuthConfig{ServiceName: "test-auth"})
	mux := http.NewServeMux()
	mux.HandleFunc("/ready", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := AuthHTTPMiddleware(reg)(mux)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	handler.ServeHTTP(rec, req)

	body := scrapeMetrics(t, reg.Gatherer())
	if !containsRouteLabel(body, "/ready") {
		t.Fatalf("expected route=/ready in metrics, got:\n%s", body)
	}
}

func TestProxyRateLimitMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy")
	reg.IncRateLimitDenied()
	reg.IncRateLimitRedisError()
	assertRequiredMetrics(t, reg.Gatherer(), []string{
		"ibex_proxy_rate_limited_total",
		"ibex_proxy_rate_limit_redis_errors_total",
	})
}
