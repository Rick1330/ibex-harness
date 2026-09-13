package http

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

type scriptedProvider struct {
	name   string
	models []string
	errs   []error
	body   string
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
	body := s.body
	if body == "" {
		body = minimalValidChatCompletionJSON
	}
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(body)),
	}, nil
}

type fakeFallbackRouter struct {
	byModel map[string]provider.Provider
	chain   []string
	deny    map[string]error
}

func (f *fakeFallbackRouter) ForOrg(_ context.Context, _ uuid.UUID, model string) (provider.Provider, error) {
	if err, ok := f.deny[model]; ok {
		return nil, err
	}
	if p, ok := f.byModel[model]; ok {
		return p, nil
	}
	return nil, provider.ErrNoProviderForModel
}

func (f *fakeFallbackRouter) FallbackChain(context.Context, uuid.UUID, string) ([]string, error) {
	return append([]string(nil), f.chain...), nil
}

func pe5xx(name string, code int) *provider.ProviderError {
	return &provider.ProviderError{ProviderName: name, StatusCode: code}
}

// peCircuitOpen mirrors MapBreakerError's circuit-open ProviderError shape.
func peCircuitOpen(name string) *provider.ProviderError {
	return &provider.ProviderError{
		ProviderName:   name,
		StatusCode:     http.StatusServiceUnavailable,
		ProviderErrMsg: "circuit breaker open",
		Reason:         provider.ErrorReasonCircuitOpen,
	}
}

func fallbackChatHandler(t *testing.T, depth int, router *fakeFallbackRouter, providers ...provider.Provider) http.Handler {
	t.Helper()
	return fallbackChatHandlerWithTrace(t, depth, router, nil, nil, providers...)
}

func fallbackChatHandlerWithTrace(
	t *testing.T,
	depth int,
	router *fakeFallbackRouter,
	tw TraceWriter,
	pool *asyncpool.Pool,
	providers ...provider.Provider,
) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), providers...)
	if err != nil {
		t.Fatal(err)
	}
	return mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config.MaxFallbackDepth = depth
		d.Validator = &chatMockValidator{res: &auth.ValidateResult{
			OrgID: uuid.MustParse(testChatOrgID), Permissions: permissions.ProxyChatCompletion,
		}}
		d.ProviderRegistry = reg
		d.ModelRouter = router
		d.Metrics = metrics.NewProxy("fallback-test")
		d.CheckpointPool = pool
		d.TraceWriter = tw
	}))
}

func postFallbackChat(t *testing.T, handler http.Handler) *httptest.ResponseRecorder {
	t.Helper()
	return postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth:    true,
		agentID: testChatAgentID,
	})
}

const fallbackModelClaudeSonnet = "claude-sonnet-4-5"

func openAIFallbackFixture(chain []string, primaryErr error) (*scriptedProvider, *scriptedProvider, *fakeFallbackRouter) {
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{primaryErr}}
	fallback := &scriptedProvider{name: "anthropic", models: []string{fallbackModelClaudeSonnet}}
	router := &fakeFallbackRouter{
		chain: chain,
		byModel: map[string]provider.Provider{
			"gpt-4o": primary, fallbackModelClaudeSonnet: fallback,
		},
	}
	return primary, fallback, router
}

func assertFallbackSuccessHeaders(t *testing.T, rec *httptest.ResponseRecorder, usedModel string) {
	t.Helper()
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "true" {
		t.Fatalf("fallback header=%q", rec.Header().Get(headerIBEXProviderFallback))
	}
	if rec.Header().Get(headerIBEXProviderUsed) != usedModel {
		t.Fatalf("used=%q", rec.Header().Get(headerIBEXProviderUsed))
	}
}

func TestUnit_ChatFallback_SuccessHeadersAndModel(t *testing.T) {
	t.Parallel()
	primary, fallback, router := openAIFallbackFixture([]string{fallbackModelClaudeSonnet}, pe5xx("openai", 503))
	rec := postFallbackChat(t, fallbackChatHandler(t, 1, router, primary, fallback))
	assertFallbackSuccessHeaders(t, rec, fallbackModelClaudeSonnet)
}

func TestUnit_ChatFallback_ExhaustNoHeaders(t *testing.T) {
	t.Parallel()
	fail := pe5xx("openai", 502)
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{fail}}
	hop := &scriptedProvider{name: "openai", models: []string{"gpt-4o-mini"}, errs: []error{fail}}
	router := &fakeFallbackRouter{
		chain:   []string{"gpt-4o-mini"},
		byModel: map[string]provider.Provider{"gpt-4o": primary, "gpt-4o-mini": hop},
	}
	rec := postFallbackChat(t, fallbackChatHandler(t, 2, router, primary, hop))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "" || rec.Header().Get(headerIBEXProviderUsed) != "" {
		t.Fatal("must not set fallback headers on exhaust")
	}
}

func TestUnit_ChatFallback_SkipDenyThenSuccess(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{pe5xx("openai", 503)}}
	ok := &scriptedProvider{name: "anthropic", models: []string{"claude-opus-4-5"}}
	router := &fakeFallbackRouter{
		chain: []string{"blocked-model", "claude-opus-4-5"},
		deny:  map[string]error{"blocked-model": modelpolicy.ErrModelNotAllowedForOrg},
		byModel: map[string]provider.Provider{
			"gpt-4o": primary, "claude-opus-4-5": ok,
		},
	}
	rec := postFallbackChat(t, fallbackChatHandler(t, 2, router, primary, ok))
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderUsed) != "claude-opus-4-5" {
		t.Fatalf("used=%q", rec.Header().Get(headerIBEXProviderUsed))
	}
}

func TestUnit_ChatFallback_Hop4xxStopsChain(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{pe5xx("openai", 503)}}
	hop429 := &scriptedProvider{
		name: "openai", models: []string{"gpt-4o-mini"},
		errs: []error{&provider.ProviderError{ProviderName: "openai", StatusCode: 429}},
	}
	second := &scriptedProvider{name: "anthropic", models: []string{"claude-sonnet-4-5"}}
	router := &fakeFallbackRouter{
		chain: []string{"gpt-4o-mini", "claude-sonnet-4-5"},
		byModel: map[string]provider.Provider{
			"gpt-4o": primary, "gpt-4o-mini": hop429, "claude-sonnet-4-5": second,
		},
	}
	rec := postFallbackChat(t, fallbackChatHandler(t, 2, router, primary, hop429, second))
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("4xx hop must stop chain without substitution headers")
	}
	if second.calls != 0 {
		t.Fatalf("second hop calls=%d want 0", second.calls)
	}
	if rec.Code == http.StatusOK {
		t.Fatal("must not succeed after ineligible hop")
	}
}

func TestUnit_ChatFallback_UnclassifiedForOrgAborts(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{pe5xx("openai", 503)}}
	ok := &scriptedProvider{name: "anthropic", models: []string{"claude-sonnet-4-5"}}
	router := &fakeFallbackRouter{
		chain: []string{"weird-hop", "claude-sonnet-4-5"},
		deny:  map[string]error{"weird-hop": errors.New("routing boom")},
		byModel: map[string]provider.Provider{
			"gpt-4o": primary, "claude-sonnet-4-5": ok,
		},
	}
	rec := postFallbackChat(t, fallbackChatHandler(t, 2, router, primary, ok))
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("unclassified ForOrg must abort without headers")
	}
	if ok.calls != 0 {
		t.Fatalf("ok hop calls=%d want 0", ok.calls)
	}
}

func TestUnit_ChatFallback_NoHeadersWhenPipelineFails(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{name: "openai", models: []string{"gpt-4o"}, errs: []error{pe5xx("openai", 503)}}
	badJSON := &scriptedProvider{
		name: "anthropic", models: []string{"claude-sonnet-4-5"}, body: "{not-json",
	}
	router := &fakeFallbackRouter{
		chain:   []string{"claude-sonnet-4-5"},
		byModel: map[string]provider.Provider{"gpt-4o": primary, "claude-sonnet-4-5": badJSON},
	}
	rec := postFallbackChat(t, fallbackChatHandler(t, 1, router, primary, badJSON))
	if rec.Code == http.StatusOK {
		t.Fatal("invalid fallback body must fail closed")
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("must not set fallback headers before response acceptance")
	}
}

func TestUnit_ChatFallback_CircuitOpenNoChainHardFailure(t *testing.T) {
	t.Parallel()
	primary, fallback, router := openAIFallbackFixture(nil, peCircuitOpen("openai"))
	rec := postFallbackChat(t, fallbackChatHandler(t, 1, router, primary, fallback))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "circuit breaker") {
		t.Fatalf("body=%s want primary circuit-open mapping", rec.Body.String())
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "" || rec.Header().Get(headerIBEXProviderUsed) != "" {
		t.Fatal("must not set fallback headers when chain empty")
	}
	if fallback.calls != 0 {
		t.Fatalf("fallback calls=%d want 0", fallback.calls)
	}
}

func TestUnit_ChatFallback_ExpiredContextSkipsFallback(t *testing.T) {
	t.Parallel()
	_, fallback, router := openAIFallbackFixture([]string{fallbackModelClaudeSonnet}, peCircuitOpen("openai"))
	org := uuid.MustParse(testChatOrgID)
	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	ctx = auth.WithContext(ctx, &auth.ValidateResult{OrgID: org})
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req = req.WithContext(ctx)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), maxFallbackDepth: 1,
		modelRouter: router, policyFallback: router,
	}
	h.handlePrimaryCompleteError(primaryCompleteErrorArgs{
		p: chatForwardParams{
			w: rec, r: req, prov: &scriptedProvider{name: "openai", models: []string{"gpt-4o"}},
			parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"},
		},
		provReq:   provider.Request{Model: "gpt-4o"},
		requestID: "req-expired",
		err:       peCircuitOpen("openai"),
	})
	if fallback.calls != 0 {
		t.Fatalf("fallback calls=%d want 0 on expired request context", fallback.calls)
	}
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("must not set fallback headers when request context is done")
	}
}

func TestUnit_classifyFallbackHopErr_AbortedContext(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	outcome, _ := classifyFallbackHopErr(ctx, pe5xx("openai", 503), provider.Request{Model: "gpt-4o"})
	if outcome != hopAbort {
		t.Fatalf("outcome=%v want hopAbort when request context is done", outcome)
	}
}

func TestUnit_ChatFallback_CircuitOpenTriggersFallback(t *testing.T) {
	t.Parallel()
	tw := &recordingTraceWriter{}
	primary, fallback, router := openAIFallbackFixture([]string{fallbackModelClaudeSonnet}, peCircuitOpen("openai"))
	handler := fallbackChatHandlerWithTrace(t, 1, router, tw, mustPool(t), primary, fallback)
	rec := postFallbackChat(t, handler)
	assertFallbackSuccessHeaders(t, rec, fallbackModelClaudeSonnet)
	tw.waitWrites(t, 1)
	got, ok := tw.last()
	if !ok {
		t.Fatal("no trace write")
	}
	assertTraceFallbackAudit(t, got, "gpt-4o", fallbackModelClaudeSonnet, provider.FallbackReasonCircuitOpen)
}

func TestUnit_ChatFallback_NeverOn429Primary(t *testing.T) {
	t.Parallel()
	primary := &scriptedProvider{
		name: "openai", models: []string{"gpt-4o"},
		errs: []error{&provider.ProviderError{ProviderName: "openai", StatusCode: 429}},
	}
	fallback := &scriptedProvider{name: "anthropic", models: []string{"claude-sonnet-4-5"}}
	router := &fakeFallbackRouter{
		chain:   []string{"claude-sonnet-4-5"},
		byModel: map[string]provider.Provider{"gpt-4o": primary, "claude-sonnet-4-5": fallback},
	}
	rec := postFallbackChat(t, fallbackChatHandler(t, 1, router, primary, fallback))
	if rec.Header().Get(headerIBEXProviderFallback) != "" {
		t.Fatal("429 must not trigger fallback")
	}
	if fallback.calls != 0 {
		t.Fatalf("fallback calls=%d", fallback.calls)
	}
}

func TestUnit_ChatFallback_DepthCapAndPolicyUnavailable(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse(testChatOrgID)
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org}))
	p := chatForwardParams{
		w: httptest.NewRecorder(), r: req,
		parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"},
	}
	provReq := provider.Request{Model: "gpt-4o"}

	depthH := chatCompletionHandler{
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
	if _, ok := depthH.tryFallbackComplete(p, provReq, provider.FallbackReason5xx); ok {
		t.Fatal("depth-1 should not succeed when first hop denied")
	}

	abortH := chatCompletionHandler{
		maxFallbackDepth: 2,
		modelRouter: &fakeFallbackRouter{
			chain: []string{"claude-sonnet-4-5"},
			deny:  map[string]error{"claude-sonnet-4-5": modelpolicy.ErrPolicyUnavailable},
		},
		policyFallback: &fakeFallbackRouter{chain: []string{"claude-sonnet-4-5"}},
	}
	if _, ok := abortH.tryFallbackComplete(p, provReq, provider.FallbackReasonCircuitOpen); ok {
		t.Fatal("policy unavailable must abort")
	}
}
