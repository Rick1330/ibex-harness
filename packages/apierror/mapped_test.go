package apierror_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/apierror"
)

func TestWriteHTTP_setsRetryAfterAndEnvelope(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	apierror.WriteHTTP(rec, "req-ra", apierror.WriteOpts{DocsBase: "https://docs.example"}, &apierror.Error{
		Code:       apierror.CodeRateLimited,
		Message:    "Upstream LLM provider rate limited",
		Detail:     "provider throttled",
		HTTPStatus: http.StatusTooManyRequests,
		RetryAfter: 30 * time.Second,
	})
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("status: %d", rec.Code)
	}
	if got := rec.Header().Get("Retry-After"); got != "30" {
		t.Fatalf("Retry-After: %q", got)
	}
	var body apierror.Response
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if body.Error.Code != apierror.CodeRateLimited {
		t.Fatalf("code: %s", body.Error.Code)
	}
	if body.Error.Detail != "provider throttled" {
		t.Fatalf("detail: %q", body.Error.Detail)
	}
	if body.Error.RequestID != "req-ra" {
		t.Fatalf("request_id: %s", body.Error.RequestID)
	}
}

func TestWriteHTTP_retryAfterRoundsUpAndClamps(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	apierror.WriteHTTP(rec, "req", apierror.WriteOpts{}, &apierror.Error{
		Code:       apierror.CodeRateLimited,
		Message:    "Upstream LLM provider rate limited",
		HTTPStatus: http.StatusTooManyRequests,
		RetryAfter: 1500 * time.Millisecond,
	})
	if got := rec.Header().Get("Retry-After"); got != "2" {
		t.Fatalf("expected ceil seconds, got %q", got)
	}

	rec2 := httptest.NewRecorder()
	apierror.WriteHTTP(rec2, "req", apierror.WriteOpts{}, &apierror.Error{
		Code:       apierror.CodeRateLimited,
		Message:    "Upstream LLM provider rate limited",
		HTTPStatus: http.StatusTooManyRequests,
		RetryAfter: 10 * time.Hour,
	})
	if got := rec2.Header().Get("Retry-After"); got != "3600" {
		t.Fatalf("expected clamp to 3600, got %q", got)
	}
}

func TestWriteHTTP_nilNoOp(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	apierror.WriteHTTP(rec, "req", apierror.WriteOpts{}, nil)
	if rec.Code != http.StatusOK || rec.Body.Len() != 0 {
		t.Fatalf("expected no write, status=%d body=%q", rec.Code, rec.Body.String())
	}
}

func TestWriteHTTP_defaultsHTTPStatusFromCode(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	apierror.WriteHTTP(rec, "req", apierror.WriteOpts{}, &apierror.Error{
		Code:    apierror.CodeProviderTimeout,
		Message: "Upstream LLM provider timed out",
	})
	if rec.Code != http.StatusGatewayTimeout {
		t.Fatalf("status: %d", rec.Code)
	}
}
