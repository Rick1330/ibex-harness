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
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
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
		body = minimalValidChatCompletionJSON
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
	handler := mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config = config.Config{ServiceName: "proxy"}
		d.ProviderRegistry = mustEmptyProviderRegistry(t)
	}))

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
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), stubLLMProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	handler := chatRouterWithProvider(t, reg, nil)

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
			reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), stubLLMProvider{
				name: "openai", models: []string{"gpt-4o"}, err: tc.provErr,
			})
			if err != nil {
				t.Fatalf("NewRegistry: %v", err)
			}

			handler := chatRouterWithProvider(t, reg, nil)

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
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/chat/completions", nil)
	handleChatCompletions(rec, req, chatCompletionHandler{
		log:      logger.Discard("proxy"),
		docsBase: "",
	})
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_ChatCompletions_missingProviderReturnsInternalError(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(llm.WithChatRequest(req.Context(), &llm.ChatCompletionRequest{
		Model: "gpt-4o", Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}))
	handleChatCompletions(rec, req, chatCompletionHandler{
		log:      logger.Discard("proxy"),
		docsBase: "",
	})
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeInternalError)) {
		t.Fatalf("body: %s", rec.Body.String())
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
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog())
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}

	handler := chatRouterWithProvider(t, reg, func(d *RouterDeps) {
		d.Validator = &chatMockValidator{res: &auth.ValidateResult{
			OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
		}}
	})

	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	// Empty registry: stream requests still 501 when no provider matches the model.
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}
