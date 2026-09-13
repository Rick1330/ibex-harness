package http

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

type scriptedProvider struct {
	name   string
	models []string
	errs   []error
	mu     sync.Mutex
	calls  int
}

func (s *scriptedProvider) Name() string              { return s.name }
func (s *scriptedProvider) SupportedModels() []string { return s.models }

func (s *scriptedProvider) Complete(_ context.Context, _ provider.Request) (provider.Response, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	i := s.calls
	s.calls++
	if i < len(s.errs) && s.errs[i] != nil {
		return provider.Response{}, s.errs[i]
	}
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(minimalValidChatCompletionJSON)),
	}, nil
}

type fakeFallbackRouter struct {
	byModel   map[string]provider.Provider
	chain     []string
	chainErr  error
	deny      map[string]error
	forOrgErr error
}

func (f *fakeFallbackRouter) ForOrg(_ context.Context, _ uuid.UUID, model string) (provider.Provider, error) {
	if f.forOrgErr != nil {
		return nil, f.forOrgErr
	}
	if err, ok := f.deny[model]; ok {
		return nil, err
	}
	if p, ok := f.byModel[model]; ok {
		return p, nil
	}
	return nil, provider.ErrNoProviderForModel
}

func (f *fakeFallbackRouter) FallbackChain(context.Context, uuid.UUID, string) ([]string, error) {
	if f.chainErr != nil {
		return nil, f.chainErr
	}
	return append([]string(nil), f.chain...), nil
}

func TestUnit_ChatFallback_SuccessHeadersAndModel(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{
		name: "openai", models: []string{"gpt-4o"},
		errs: []error{&provider.ProviderError{ProviderName: "openai", StatusCode: 503}},
	}
	fallback := &scriptedProvider{name: "anthropic", models: []string{"claude-sonnet-4-5"}}
	router := &fakeFallbackRouter{
		chain: []string{"claude-sonnet-4-5"},
		byModel: map[string]provider.Provider{
			"gpt-4o":            primary,
			"claude-sonnet-4-5": fallback,
		},
	}
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), primary, fallback)
	if err != nil {
		t.Fatal(err)
	}
	met := metrics.NewProxy("fallback-success")
	handler := mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config.MaxFallbackDepth = 1
		d.Validator = &chatMockValidator{res: &auth.ValidateResult{
			OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
		}}
		d.ProviderRegistry = reg
		d.ModelRouter = router
		d.Metrics = met
	}))
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "true" {
		t.Fatalf("fallback header=%q", rec.Header().Get(headerIBEXProviderFallback))
	}
	if rec.Header().Get(headerIBEXProviderUsed) != "claude-sonnet-4-5" {
		t.Fatalf("used=%q", rec.Header().Get(headerIBEXProviderUsed))
	}
}

func TestUnit_ChatFallback_ExhaustNoHeaders(t *testing.T) {
	t.Parallel()
	fail := &provider.ProviderError{ProviderName: "openai", StatusCode: 502}
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{fail}}
	hop := &scriptedProvider{name: "openai", models: []string{"gpt-4o-mini"}, errs: []error{fail}}
	router := &fakeFallbackRouter{
		chain: []string{"gpt-4o-mini"},
		byModel: map[string]provider.Provider{
			"gpt-4o":      primary,
			"gpt-4o-mini": hop,
		},
	}
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), primary, hop)
	if err != nil {
		t.Fatal(err)
	}
	handler := mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config.MaxFallbackDepth = 2
		d.Validator = &chatMockValidator{res: &auth.ValidateResult{
			OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
		}}
		d.ProviderRegistry = reg
		d.ModelRouter = router
	}))
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusBadGateway && rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("must not set fallback headers on exhaust")
	}
	if rec.Header().Get(headerIBEXProviderUsed) != "" {
		t.Fatal("must not set used header on exhaust")
	}
}

func TestUnit_ChatFallback_SkipDenyThenSuccess(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{
		name: "openai", models: []string{"gpt-4o"},
		errs: []error{&provider.ProviderError{ProviderName: "openai", StatusCode: 503}},
	}
	ok := &scriptedProvider{name: "anthropic", models: []string{"claude-opus-4-5"}}
	router := &fakeFallbackRouter{
		chain: []string{"blocked-model", "claude-opus-4-5"},
		deny:  map[string]error{"blocked-model": modelpolicy.ErrModelNotAllowedForOrg},
		byModel: map[string]provider.Provider{
			"gpt-4o":          primary,
			"claude-opus-4-5": ok,
		},
	}
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), primary, ok)
	if err != nil {
		t.Fatal(err)
	}
	handler := mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config.MaxFallbackDepth = 2
		d.Validator = &chatMockValidator{res: &auth.ValidateResult{
			OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
		}}
		d.ProviderRegistry = reg
		d.ModelRouter = router
	}))
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderUsed) != "claude-opus-4-5" {
		t.Fatalf("used=%q", rec.Header().Get(headerIBEXProviderUsed))
	}
}

func TestUnit_ChatFallback_DepthCap(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		maxFallbackDepth: 1,
		modelRouter: &fakeFallbackRouter{
			chain: []string{"a", "b"},
			deny: map[string]error{
				"a": modelpolicy.ErrModelNotAllowedForOrg,
				"b": modelpolicy.ErrModelNotAllowedForOrg,
			},
		},
		policyFallback: &fakeFallbackRouter{chain: []string{"a", "b"}},
	}
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: uuid.MustParse(testChatOrgID),
	}))
	_, ok := h.tryFallbackComplete(chatForwardParams{
		w: httptest.NewRecorder(), r: req,
		parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"},
	}, provider.Request{Model: "gpt-4o"}, provider.FallbackReason5xx)
	if ok {
		t.Fatal("depth-1 should not reach second hop success when both denied")
	}
}

func TestUnit_ChatFallback_PolicyUnavailableAborts(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		maxFallbackDepth: 2,
		modelRouter: &fakeFallbackRouter{
			chain: []string{"claude-sonnet-4-5"},
			deny:  map[string]error{"claude-sonnet-4-5": modelpolicy.ErrPolicyUnavailable},
		},
		policyFallback: &fakeFallbackRouter{chain: []string{"claude-sonnet-4-5"}},
	}
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{
		OrgID: uuid.MustParse(testChatOrgID),
	}))
	_, ok := h.tryFallbackComplete(chatForwardParams{
		w: httptest.NewRecorder(), r: req,
		parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"},
	}, provider.Request{Model: "gpt-4o"}, provider.FallbackReasonCircuitOpen)
	if ok {
		t.Fatal("policy unavailable must abort")
	}
}

func TestUnit_TruncateChain_Concurrent(t *testing.T) {
	t.Parallel()
	chain := []string{"a", "b", "c"}
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			got := modelpolicy.TruncateChain(chain, 1)
			if len(got) != 1 || got[0] != "a" {
				t.Errorf("got=%v", got)
			}
		}()
	}
	wg.Wait()
}

func TestUnit_ChatFallback_NeverAfterPrimarySuccess(t *testing.T) {
	t.Parallel()
	// Primary Complete fails before stream → fallback still allowed (covered elsewhere).
	// Ensure 4xx is not eligible even when chain exists.
	primary := &scriptedProvider{
		name: "openai", models: []string{"gpt-4o"},
		errs: []error{&provider.ProviderError{ProviderName: "openai", StatusCode: 429}},
	}
	fallback := &scriptedProvider{name: "anthropic", models: []string{"claude-sonnet-4-5"}}
	router := &fakeFallbackRouter{
		chain: []string{"claude-sonnet-4-5"},
		byModel: map[string]provider.Provider{
			"gpt-4o":            primary,
			"claude-sonnet-4-5": fallback,
		},
	}
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), primary, fallback)
	if err != nil {
		t.Fatal(err)
	}
	handler := mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Validator = &chatMockValidator{res: &auth.ValidateResult{
			OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
		}}
		d.ProviderRegistry = reg
		d.ModelRouter = router
	}))
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("429 must not trigger fallback")
	}
}
