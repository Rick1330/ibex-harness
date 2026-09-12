package http

import (
	"context"
	"errors"
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

var testOrgID = uuid.MustParse("550e8400-e29b-41d4-a716-446655440001")

func TestUnit_ProviderRouting_KnownModelAttachesProvider(t *testing.T) {
	t.Parallel()
	var gotName string
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p, ok := provider.ProviderFromContext(r.Context())
		if !ok {
			t.Fatal("provider missing from context")
		}
		gotName = p.Name()
		w.WriteHeader(http.StatusOK)
	})
	rec := serveProviderRouting(t, routingCase{model: "gpt-4o", next: next})
	assertRoutingStatus(t, rec, http.StatusOK, "")
	if gotName != "openai" {
		t.Fatalf("provider=%q", gotName)
	}
}

func TestUnit_ProviderRouting_UnknownModel501(t *testing.T) {
	t.Parallel()
	called := false
	next := http.HandlerFunc(func(http.ResponseWriter, *http.Request) { called = true })
	rec := serveProviderRouting(t, routingCase{model: "unknown-model", next: next})
	if called {
		t.Fatal("next must not run")
	}
	assertRoutingStatus(t, rec, http.StatusNotImplemented, apierror.CodeProviderNotConfigured)
}

func TestUnit_ProviderRouting_Deny403(t *testing.T) {
	t.Parallel()
	reg := mustOrgAwareRegistry(t, &staticPolicyLoader{policies: []modelpolicy.Policy{{
		Pattern: "gpt-*", Allowed: false, Priority: 1,
	}}})
	rec := serveProviderRouting(t, routingCase{
		model: "gpt-4o", orgID: testOrgID, resolver: reg, next: refuseNext(t),
	})
	assertRoutingStatus(t, rec, http.StatusForbidden, apierror.CodeModelNotAllowed)
}

func TestUnit_ProviderRouting_EmptyModelUsesAgentDefault(t *testing.T) {
	t.Parallel()
	var gotModel, gotProvider string
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parsed, ok := llm.ChatRequestFromContext(r.Context())
		if !ok {
			t.Fatal("chat request missing")
		}
		gotModel = parsed.Model
		p, ok := provider.ProviderFromContext(r.Context())
		if !ok {
			t.Fatal("provider missing")
		}
		gotProvider = p.Name()
		w.WriteHeader(http.StatusOK)
	})
	rec := serveProviderRouting(t, routingCase{
		model: "", orgID: testOrgID, agentOrg: testOrgID,
		defaults: staticAgentDefaults{defaults: modelpolicy.AgentDefaults{DefaultModel: "gpt-4o"}},
		next:     next,
	})
	assertRoutingStatus(t, rec, http.StatusOK, "")
	if gotModel != "gpt-4o" || gotProvider != "openai" {
		t.Fatalf("model=%q provider=%q", gotModel, gotProvider)
	}
}

func TestUnit_ProviderRouting_PolicyUnavailable503(t *testing.T) {
	t.Parallel()
	reg := mustOrgAwareRegistry(t, errPolicyLoader{})
	rec := serveProviderRouting(t, routingCase{
		model: "gpt-4o", orgID: testOrgID, resolver: reg, next: refuseNext(t),
	})
	assertRoutingStatus(t, rec, http.StatusServiceUnavailable, apierror.CodeServiceDegraded)
}

func TestUnit_ProviderRouting_MissingOrg503(t *testing.T) {
	t.Parallel()
	rec := serveProviderRouting(t, routingCase{
		model: "gpt-4o", omitAuth: true, next: refuseNext(t),
	})
	assertRoutingStatus(t, rec, http.StatusServiceUnavailable, "")
}

func TestUnit_ProviderRouting_AgentOrgMismatchRejects(t *testing.T) {
	t.Parallel()
	otherOrg := uuid.MustParse("550e8400-e29b-41d4-a716-446655440099")
	rec := serveProviderRouting(t, routingCase{
		model: "", orgID: testOrgID, agentOrg: otherOrg,
		defaults: staticAgentDefaults{defaults: modelpolicy.AgentDefaults{DefaultModel: "gpt-4o"}},
		next:     refuseNext(t),
	})
	assertRoutingStatus(t, rec, http.StatusBadRequest, "")
}

func TestUnit_ProviderRouting_AgentDefaultLoadError503(t *testing.T) {
	t.Parallel()
	rec := serveProviderRouting(t, routingCase{
		model: "", orgID: testOrgID, agentOrg: testOrgID,
		defaults: errAgentDefaults{}, next: refuseNext(t),
	})
	assertRoutingStatus(t, rec, http.StatusServiceUnavailable, "")
}

func TestUnit_ChatParse_EmptyModelAllowed(t *testing.T) {
	t.Parallel()
	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
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

type routingCase struct {
	model    string
	orgID    uuid.UUID
	agentOrg uuid.UUID
	omitAuth bool
	resolver ProviderResolver
	defaults modelpolicy.AgentDefaultLoader
	next     http.Handler
}

func serveProviderRouting(t *testing.T, tc routingCase) *httptest.ResponseRecorder {
	t.Helper()
	org := tc.orgID
	if org == uuid.Nil {
		org = testOrgID
	}
	resolver := tc.resolver
	if resolver == nil {
		resolver = modelpolicy.PassthroughRegistry{Base: mustOpenAIRegistry(t)}
	}
	h := ProviderRoutingMiddleware(providerRoutingOpts{
		resolver: resolver, agentDefaults: tc.defaults, log: logger.Discard("proxy"),
	})(tc.next)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	if !tc.omitAuth {
		req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
		req = attachAgentIfNeeded(req, tc, org)
	}
	req = req.WithContext(llm.WithChatRequest(req.Context(), &llm.ChatCompletionRequest{
		Model: tc.model, Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func attachAgentIfNeeded(req *http.Request, tc routingCase, org uuid.UUID) *http.Request {
	if tc.agentOrg == uuid.Nil && tc.model != "" {
		return req
	}
	agentOrg := tc.agentOrg
	if agentOrg == uuid.Nil {
		agentOrg = org
	}
	return req.WithContext(WithAgent(req.Context(), auth.AgentRecord{
		ID: uuid.MustParse("550e8400-e29b-41d4-a716-446655440002"), OrgID: agentOrg, Status: "active",
	}))
}

func mustOrgAwareRegistry(t *testing.T, loader modelpolicy.PolicyLoader) *modelpolicy.OrgAwareRegistry {
	t.Helper()
	cache, err := modelpolicy.NewCache(loader, modelpolicy.Config{}, modelpolicy.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	reg, err := modelpolicy.NewOrgAwareRegistry(mustOpenAIRegistry(t), cache, modelpolicy.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	return reg
}

func refuseNext(t *testing.T) http.Handler {
	t.Helper()
	return http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("must not continue")
	})
}

func assertRoutingStatus(t *testing.T, rec *httptest.ResponseRecorder, want int, code apierror.Code) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status=%d want=%d body=%s", rec.Code, want, rec.Body.String())
	}
	if code != "" && !strings.Contains(rec.Body.String(), string(code)) {
		t.Fatalf("body missing %s: %s", code, rec.Body.String())
	}
}

func mustOpenAIRegistry(t *testing.T) *provider.Registry {
	t.Helper()
	reg, err := provider.NewRegistry(
		provider.BuiltInCapabilityCatalog(),
		stubLLMProvider{name: "openai", models: []string{"gpt-4o"}},
	)
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	return reg
}

type staticPolicyLoader struct{ policies []modelpolicy.Policy }

func (s *staticPolicyLoader) LoadOrg(context.Context, uuid.UUID) ([]modelpolicy.Policy, error) {
	return append([]modelpolicy.Policy(nil), s.policies...), nil
}

type errPolicyLoader struct{}

func (errPolicyLoader) LoadOrg(context.Context, uuid.UUID) ([]modelpolicy.Policy, error) {
	return nil, errors.New("db down")
}

type staticAgentDefaults struct{ defaults modelpolicy.AgentDefaults }

func (s staticAgentDefaults) Load(context.Context, uuid.UUID, uuid.UUID) (modelpolicy.AgentDefaults, error) {
	return s.defaults, nil
}

type errAgentDefaults struct{}

func (errAgentDefaults) Load(context.Context, uuid.UUID, uuid.UUID) (modelpolicy.AgentDefaults, error) {
	return modelpolicy.AgentDefaults{}, errors.New("db down")
}
