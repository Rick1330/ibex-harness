package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
)

const testChatOrgID = "550e8400-e29b-41d4-a716-446655440001"

type chatMockValidator struct {
	res *auth.ValidateResult
	err error
}

func (m *chatMockValidator) Validate(_ context.Context, _ string) (*auth.ValidateResult, error) {
	return m.res, m.err
}

func TestChatCompletions_validJSON_returns501(t *testing.T) {
	validator := &chatMockValidator{res: &auth.ValidateResult{
		OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
	}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080", MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := newTestRouter(cfg, validator, ratelimit.Noop())

	body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", "550e8400-e29b-41d4-a716-446655440000")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeProviderNotConfigured) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestChatCompletions_invalidJSON_returns400(t *testing.T) {
	validator := &chatMockValidator{res: &auth.ValidateResult{
		OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
	}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080", MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := newTestRouter(cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{bad`))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", "550e8400-e29b-41d4-a716-446655440000")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeInvalidJSON) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestChatCompletions_noAuth_returns401(t *testing.T) {
	validator := &chatMockValidator{res: &auth.ValidateResult{OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080", MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := newTestRouter(cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestChatCompletions_missingAgentID_returns400(t *testing.T) {
	validator := &chatMockValidator{res: &auth.ValidateResult{
		OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
	}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080", MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := newTestRouter(cfg, validator, ratelimit.Noop())

	body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeMissingAgentID) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestChatCompletions_emptyMessages_returns400(t *testing.T) {
	validator := &chatMockValidator{res: &auth.ValidateResult{
		OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
	}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080", MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := newTestRouter(cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{"model":"m","messages":[]}`))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", "550e8400-e29b-41d4-a716-446655440000")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestChatCompletions_validatorError_returns503(t *testing.T) {
	validator := &chatMockValidator{err: auth.ErrAuthUnavailable}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080", MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}
	handler := newTestRouter(cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{"model":"m","messages":[]}`))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", "550e8400-e29b-41d4-a716-446655440000")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d", rec.Code)
	}
}
