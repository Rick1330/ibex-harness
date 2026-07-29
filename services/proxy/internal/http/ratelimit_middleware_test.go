package http

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
