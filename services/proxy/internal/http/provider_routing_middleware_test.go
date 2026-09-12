package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

func TestUnit_ProviderRouting_KnownModelAttachesProvider(t *testing.T) {
	t.Parallel()
	var gotName string
	var called bool
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		p, ok := provider.ProviderFromContext(r.Context())
		if !ok {
			t.Fatal("provider missing from context")
		}
		gotName = p.Name()
		w.WriteHeader(http.StatusOK)
	})

	rec := serveProviderRouting(t, "gpt-4o", next, nil)
	if !called {
		t.Fatal("handler not called")
	}
	if gotName != "openai" {
		t.Fatalf("provider=%q", gotName)
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestUnit_ProviderRouting_UnknownModel501(t *testing.T) {
	t.Parallel()
	called := false
	next := http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		called = true
	})

	rec := serveProviderRouting(t, "unknown-model", next, nil)
	if called {
		t.Fatal("handler must not run for unknown model")
	}
	if rec.Code != http.StatusNotImplemented {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeProviderNotConfigured)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestUnit_ProviderRouting_Deny403(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	base, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), stubLLMProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatal(err)
	}
	loader := &staticPolicyLoader{policies: []modelpolicy.Policy{{
		Pattern: "gpt-*", Allowed: false, Priority: 1,
	}}}
	cache, err := modelpolicy.NewCache(loader, modelpolicy.Config{}, modelpolicy.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	reg, err := modelpolicy.NewOrgAwareRegistry(base, cache, modelpolicy.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	next := http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("must not continue")
	})
	h := ProviderRoutingMiddleware(providerRoutingOpts{
		resolver: reg,
		log:      logger.Discard("proxy"),
	})(next)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	req = req.WithContext(llm.WithChatRequest(req.Context(), &llm.ChatCompletionRequest{
		Model: "gpt-4o", Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeModelNotAllowed)) {
		t.Fatalf("body=%s", rec.Body.String())
	}
}

func TestUnit_ProviderRouting_EmptyModelUsesAgentDefault(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	agentID := uuid.MustParse("550e8400-e29b-41d4-a716-446655440002")
	var called bool
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})
	h := ProviderRoutingMiddleware(providerRoutingOpts{
		resolver: modelpolicy.PassthroughRegistry{Base: mustOpenAIRegistry(t)},
		agentDefaults: staticAgentDefaults{defaults: modelpolicy.AgentDefaults{DefaultModel: "gpt-4o"}},
		log:           logger.Discard("proxy"),
	})(next)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	req = req.WithContext(WithAgent(req.Context(), auth.AgentRecord{ID: agentID, OrgID: org, Status: "active"}))
	req = req.WithContext(llm.WithChatRequest(req.Context(), &llm.ChatCompletionRequest{
		Model: "", Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if !called || rec.Code != http.StatusOK {
		t.Fatalf("called=%v status=%d body=%s", called, rec.Code, rec.Body.String())
	}
}

func TestUnit_ChatParse_EmptyModelAllowed(t *testing.T) {
	t.Parallel()
	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})
	h := ChatParseMiddleware(chatParseOpts{docsBase: ""})(next)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"","messages":[{"role":"user","content":"hi"}]}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if !called || rec.Code != http.StatusOK {
		t.Fatalf("parse should allow empty model: called=%v status=%d body=%s", called, rec.Code, rec.Body.String())
	}
}

func serveProviderRouting(t *testing.T, model string, next http.Handler, defaults modelpolicy.AgentDefaultLoader) *httptest.ResponseRecorder {
	t.Helper()
	reg := mustOpenAIRegistry(t)
	h := ProviderRoutingMiddleware(providerRoutingOpts{
		resolver:      modelpolicy.PassthroughRegistry{Base: reg},
		agentDefaults: defaults,
		log:           logger.Discard("proxy"),
		docsBase:      "",
	})(next)
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	req = req.WithContext(llm.WithChatRequest(req.Context(), &llm.ChatCompletionRequest{
		Model: model, Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func mustOpenAIRegistry(t *testing.T) *provider.Registry {
	t.Helper()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), stubLLMProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	return reg
}

type staticPolicyLoader struct {
	policies []modelpolicy.Policy
}

func (s *staticPolicyLoader) LoadOrg(context.Context, uuid.UUID) ([]modelpolicy.Policy, error) {
	return append([]modelpolicy.Policy(nil), s.policies...), nil
}

type staticAgentDefaults struct {
	defaults modelpolicy.AgentDefaults
}

func (s staticAgentDefaults) Load(context.Context, uuid.UUID, uuid.UUID) (modelpolicy.AgentDefaults, error) {
	return s.defaults, nil
}
