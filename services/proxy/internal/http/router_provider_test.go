package http

import (
	"context"
	"errors"
	"io"
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
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

type stubLLMProvider struct {
	name   string
	models []string
	body   string
	err    error
}

func (s stubLLMProvider) Complete(_ context.Context, _ provider.Request) (provider.Response, error) {
	if s.err != nil {
		return provider.Response{}, s.err
	}
	body := s.body
	if body == "" {
		body = `{"choices":[{"message":{"role":"assistant","content":"ok"}}]}`
	}
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(body)),
	}, nil
}

func (s stubLLMProvider) Name() string { return s.name }

func (s stubLLMProvider) SupportedModels() []string { return s.models }

func TestUnit_NewRouter_nilProviderRegistryUsesEmptyRegistry(t *testing.T) {
	t.Parallel()
	handler := NewRouter(RouterDeps{
		Config:        config.Config{ServiceName: "proxy"},
		Logger:        logger.Discard("proxy"),
		Metrics:       metrics.NewProxy("test"),
		Tracer:        telemetry.NoopTracer("proxy"),
		Validator:     defaultChatValidator(),
		AgentVerifier: passAgentVerifier{},
		Limiter:       ratelimit.Noop(),
		Health:        testHealthServer(),
	})

	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeProviderNotConfigured)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestUnit_ChatCompletions_registeredProviderForwardsResponse(t *testing.T) {
	t.Parallel()
	reg, err := provider.NewRegistry(stubLLMProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	handler := NewRouter(RouterDeps{
		Config:           chatTestConfig(),
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        defaultChatValidator(),
		AgentVerifier:    passAgentVerifier{},
		Limiter:          ratelimit.Noop(),
		Health:           testHealthServer(),
		ProviderRegistry: reg,
	})

	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "assistant") {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestUnit_ChatCompletions_providerErrorMapsToHTTPStatus(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name       string
		provErr    error
		wantStatus int
		wantCode   apierror.Code
	}{
		{
			name:       "provider 400",
			provErr:    &provider.ProviderError{StatusCode: http.StatusBadRequest, ProviderErrMsg: "bad field"},
			wantStatus: http.StatusBadRequest,
			wantCode:   apierror.CodeInvalidRequest,
		},
		{
			name: "provider 429",
			provErr: &provider.ProviderError{
				StatusCode: http.StatusTooManyRequests,
				RetryAfter: 30 * time.Second,
			},
			wantStatus: http.StatusTooManyRequests,
			wantCode:   apierror.CodeRateLimited,
		},
		{
			name:       "provider timeout",
			provErr:    context.DeadlineExceeded,
			wantStatus: http.StatusGatewayTimeout,
			wantCode:   apierror.CodeProviderTimeout,
		},
		{
			name:       "provider unavailable",
			provErr:    errors.New("connection refused"),
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   apierror.CodeProviderUnavailable,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			reg, err := provider.NewRegistry(stubLLMProvider{
				name: "openai", models: []string{"gpt-4o"}, err: tc.provErr,
			})
			if err != nil {
				t.Fatalf("NewRegistry: %v", err)
			}

			handler := NewRouter(RouterDeps{
				Config:           chatTestConfig(),
				Logger:           logger.Discard("proxy"),
				Metrics:          metrics.NewProxy("test"),
				Tracer:           telemetry.NoopTracer("proxy"),
				Validator:        defaultChatValidator(),
				AgentVerifier:    passAgentVerifier{},
				Limiter:          ratelimit.Noop(),
				Health:           testHealthServer(),
				ProviderRegistry: reg,
			})

			rec := postChat(t, handler, chatRequestOpts{
				body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
				auth:    true,
				agentID: testChatAgentID,
			})
			if rec.Code != tc.wantStatus {
				t.Fatalf("status: got %d want %d body=%s", rec.Code, tc.wantStatus, rec.Body.String())
			}
			if !strings.Contains(rec.Body.String(), string(tc.wantCode)) {
				t.Fatalf("body: %s", rec.Body.String())
			}
			if tc.wantCode == apierror.CodeRateLimited && rec.Header().Get("Retry-After") != "30" {
				t.Fatalf("retry-after: %q", rec.Header().Get("Retry-After"))
			}
		})
	}
}

func TestUnit_HandleChatCompletions_delegatesToServe(t *testing.T) {
	t.Parallel()
	reg, err := provider.NewRegistry()
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/chat/completions", nil)
	handleChatCompletions(rec, req, chatCompletionHandler{
		log:         logger.Discard("proxy"),
		docsBase:    "",
		providerReg: reg,
	})
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_writeChatParseError_maxBytes(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	writeChatParseError(rec, "req-id", "", &http.MaxBytesError{Limit: 1})
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_writeChatParseError_invalidJSON(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	writeChatParseError(rec, "req-id", "", errors.New("bad json"))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_parseAndValidateChatRequest_headerValidation(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", "not-a-uuid")

	_, ok := parseAndValidateChatRequest(rec, req, "req-id", "")
	if ok {
		t.Fatal("expected validation failure")
	}
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_chatCompletionHandler_logsParsedRequest(t *testing.T) {
	t.Parallel()
	reg, err := provider.NewRegistry()
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	handler := NewRouter(RouterDeps{
		Config:           chatTestConfig(),
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        &chatMockValidator{res: &auth.ValidateResult{OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion}},
		AgentVerifier:    passAgentVerifier{},
		Limiter:          ratelimit.Noop(),
		Health:           testHealthServer(),
		ProviderRegistry: reg,
	})

	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}
