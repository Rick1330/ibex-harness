package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

func TestUnit_writeProviderFailure_mapsViaProviderPackage(t *testing.T) {
	t.Parallel()
	rec := writeProviderFailureRec(t, &provider.ProviderError{
		ProviderName: "openai",
		StatusCode:   http.StatusTooManyRequests,
		RetryAfter:   30 * time.Second,
	})
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("status: %d", rec.Code)
	}
	if rec.Header().Get("Retry-After") != "30" {
		t.Fatalf("Retry-After: %q", rec.Header().Get("Retry-After"))
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeRateLimited)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestUnit_writeProviderFailure_canceledNoWrite(t *testing.T) {
	t.Parallel()
	rec := writeProviderFailureRec(t, context.Canceled)
	if rec.Body.Len() != 0 {
		t.Fatalf("expected empty body, got %s", rec.Body.String())
	}
}

func TestUnit_Streaming_PreStreamError(t *testing.T) {
	t.Parallel()
	handler := preStreamErrorHandler(t)
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	ct := rec.Header().Get("Content-Type")
	if strings.Contains(ct, "text/event-stream") {
		t.Fatalf("expected JSON envelope, Content-Type=%q", ct)
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeProviderUnavailable)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestUnit_writeProviderFailure_transport(t *testing.T) {
	t.Parallel()
	rec := writeProviderFailureRec(t, errors.New("connection refused"))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d", rec.Code)
	}
}

func writeProviderFailureRec(t *testing.T, err error) *httptest.ResponseRecorder {
	t.Helper()
	h := chatCompletionHandler{log: logger.Discard("proxy"), docsBase: ""}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	h.writeProviderFailure(providerFailureParams{
		w: rec, r: req, err: err, requestID: "req-1",
	})
	return rec
}

func preStreamErrorHandler(t *testing.T) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(stubLLMProvider{
		name:   "openai",
		models: []string{"gpt-4o"},
		err: &provider.ProviderError{
			ProviderName: "openai",
			StatusCode:   http.StatusServiceUnavailable,
		},
	})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	return mustNewRouter(t, RouterDeps{
		Config:           chatTestConfig(),
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        &chatMockValidator{res: &auth.ValidateResult{OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion}},
		AgentVerifier:    passAgentVerifier{},
		Limiter:          ratelimit.Noop(),
		Health:           testHealthServer(),
		ProviderRegistry: reg,
	})
}
