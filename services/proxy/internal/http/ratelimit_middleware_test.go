package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

type mockLimiter struct {
	result ratelimit.Result
	err    error
}

func (m *mockLimiter) Check(_ context.Context, _, _ uuid.UUID) (ratelimit.Result, error) {
	return m.result, m.err
}

func assertRateLimitHeaders(t *testing.T, rec *httptest.ResponseRecorder, limit, remaining string) {
	t.Helper()
	if got := rec.Header().Get("X-RateLimit-Limit"); got != limit {
		t.Fatalf("limit header: got %q want %q", got, limit)
	}
	if got := rec.Header().Get("X-RateLimit-Remaining"); got != remaining {
		t.Fatalf("remaining header: got %q want %q", got, remaining)
	}
}

func TestRateLimitMiddleware_allowed(t *testing.T) {
	t.Parallel()

	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	limiter := &mockLimiter{result: ratelimit.Result{
		Allowed:   true,
		Limit:     60,
		Remaining: 59,
		ResetUnix: time.Now().UTC().Unix() + 30,
	}}

	handler := RateLimitMiddleware(limiter, logger.Discard("proxy"), metrics.NewProxy("test"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	assertRateLimitHeaders(t, rec, "60", "59")
}

func TestRateLimitMiddleware_denied(t *testing.T) {
	t.Parallel()

	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	reset := time.Now().UTC().Unix() + 42
	limiter := &mockLimiter{result: ratelimit.Result{
		Allowed:    false,
		Limit:      60,
		Remaining:  0,
		ResetUnix:  reset,
		RetryAfter: 42 * time.Second,
	}}

	handler := RateLimitMiddleware(limiter, logger.Discard("proxy"), metrics.NewProxy("test"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get("Retry-After") == "" {
		t.Fatal("missing Retry-After")
	}
	assertRateLimitHeaders(t, rec, "60", "0")

	var body struct {
		Error struct {
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Error.Code != string(apierror.CodeRateLimited) {
		t.Fatalf("code: %q", body.Error.Code)
	}
}

func TestRateLimitMiddleware_BackendFailureFailsClosed(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	reg := metrics.NewProxy("ratelimit-failure-test")
	called := false
	handler := RateLimitMiddleware(&mockLimiter{err: errors.New("redis unavailable")}, logger.Discard("proxy"), reg)(
		http.HandlerFunc(func(http.ResponseWriter, *http.Request) { called = true }),
	)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if called {
		t.Fatal("downstream handler was called while shared rate-limit state was unavailable")
	}
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=%d body=%s", rec.Code, http.StatusServiceUnavailable, rec.Body.String())
	}
	if got := rec.Header().Get("Retry-After"); got != "5" {
		t.Fatalf("Retry-After=%q want 5 seconds", got)
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeServiceDegraded)) {
		t.Fatalf("body does not report service degradation: %s", rec.Body.String())
	}
	assertCounterValue(t, reg, "ibex_proxy_rate_limit_redis_errors_total", 1)
}

func assertCounterValue(t *testing.T, reg *metrics.ProxyRegistry, name string, want float64) {
	t.Helper()
	families, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, family := range families {
		if family.GetName() != name {
			continue
		}
		if len(family.GetMetric()) == 0 {
			t.Fatalf("metric %s has no samples", name)
		}
		if got := family.GetMetric()[0].GetCounter().GetValue(); got != want {
			t.Fatalf("metric %s=%v want %v", name, got, want)
		}
		return
	}
	t.Fatalf("metric %s not found", name)
}

func TestRetryAfterSeconds(t *testing.T) {
	t.Parallel()
	if got := retryAfterSeconds(0); got != 1 {
		t.Fatalf("zero duration: %d", got)
	}
	if got := retryAfterSeconds(500 * time.Millisecond); got != 1 {
		t.Fatalf("half second: %d", got)
	}
	if got := retryAfterSeconds(2 * time.Second); got != 2 {
		t.Fatalf("two seconds: %d", got)
	}
}
