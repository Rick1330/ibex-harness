package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"

	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/google/uuid"
)

type mockLimiter struct {
	result ratelimit.Result
	err    error
}

func (m *mockLimiter) Check(_ context.Context, _, _ uuid.UUID) (ratelimit.Result, error) {
	return m.result, m.err
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

	handler := RateLimitMiddleware(limiter, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID.String()}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get("X-RateLimit-Limit") != "60" {
		t.Fatalf("limit header: %q", rec.Header().Get("X-RateLimit-Limit"))
	}
	if rec.Header().Get("X-RateLimit-Remaining") != "59" {
		t.Fatalf("remaining header: %q", rec.Header().Get("X-RateLimit-Remaining"))
	}
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

	handler := RateLimitMiddleware(limiter, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID.String()}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get("Retry-After") == "" {
		t.Fatal("missing Retry-After")
	}
	if rec.Header().Get("X-RateLimit-Remaining") != "0" {
		t.Fatalf("remaining: %q", rec.Header().Get("X-RateLimit-Remaining"))
	}

	var body struct {
		Error struct {
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Error.Code != proxyerrors.CodeRateLimited {
		t.Fatalf("code: %q", body.Error.Code)
	}
}

func TestRateLimitMiddleware_failOpen(t *testing.T) {
	t.Parallel()

	orgID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440000")
	limiter := &mockLimiter{err: errors.New("redis down")}

	handler := RateLimitMiddleware(limiter, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: orgID.String()}))
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected fail-open 200, got %d", rec.Code)
	}
}

func TestRateLimitMiddleware_missingAuthContext(t *testing.T) {
	t.Parallel()

	handler := RateLimitMiddleware(&mockLimiter{}, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
		}),
	)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status: %d", rec.Code)
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
