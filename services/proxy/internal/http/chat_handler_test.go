package http

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
)

type chatMockValidator struct {
	res *auth.ValidateResult
	err error
}

func (m *chatMockValidator) Validate(_ context.Context, _ string) (*auth.ValidateResult, error) {
	return m.res, m.err
}

func TestChatCompletions_validJSON_returns501(t *testing.T) {
	validator := &chatMockValidator{res: &auth.ValidateResult{
		OrgID: "org-1", Permissions: permissions.ProxyChatCompletion,
	}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080"}
	handler := NewRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), metrics.New(), validator)

	body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
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
		OrgID: "org-1", Permissions: permissions.ProxyChatCompletion,
	}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080"}
	handler := NewRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), metrics.New(), validator)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{bad`))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
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
	validator := &chatMockValidator{res: &auth.ValidateResult{OrgID: "org-1", Permissions: permissions.ProxyChatCompletion}}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080"}
	handler := NewRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), metrics.New(), validator)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestChatCompletions_validatorError_returns503(t *testing.T) {
	validator := &chatMockValidator{err: auth.ErrAuthUnavailable}
	cfg := config.Config{Environment: "test", ServiceName: "proxy", Port: "8080"}
	handler := NewRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), metrics.New(), validator)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{"model":"m","messages":[]}`))
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d", rec.Code)
	}
}
