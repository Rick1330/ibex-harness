package http

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

type fakeContextAssembler struct {
	calls   atomic.Int32
	result  contextclient.AssembleResult
	lastReq contextclient.AssembleParams
}

func (f *fakeContextAssembler) Assemble(_ context.Context, req contextclient.AssembleParams) contextclient.AssembleResult {
	f.calls.Add(1)
	f.lastReq = req
	return f.result
}

type wantContextHeaders struct {
	memories string
	tokens   string
	fallback string
}

func contextTestAuthCtx(t *testing.T) context.Context {
	t.Helper()
	org := uuid.MustParse(testChatOrgID)
	agent := uuid.MustParse(testChatAgentID)
	ctx := auth.WithContext(context.Background(), &auth.ValidateResult{OrgID: org})
	return WithAgent(ctx, auth.AgentRecord{ID: agent, OrgID: org})
}

func baseChatMessages() []llm.Message {
	return []llm.Message{
		{Role: "system", Content: "client system"},
		{Role: "user", Content: "hello"},
	}
}

func directiveCtx(ctx context.Context) context.Context {
	return WithResolvedDirective(ctx, directive.Resolved{
		Content: "org directive", InjectionMode: "system_append", VersionID: uuid.New(),
	})
}

func contextHandler(enabled bool, client contextAssembler) chatCompletionHandler {
	return chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: enabled, contextClient: client,
	}
}

func assertNoContextHeaders(t *testing.T, h http.Header) {
	t.Helper()
	for _, name := range []string{headerMemoriesInjected, headerContextTokens, headerContextFallback} {
		if got := h.Get(name); got != "" {
			t.Fatalf("%s=%q want omitted", name, got)
		}
	}
}

func assertContextHeaders(t *testing.T, h http.Header, want wantContextHeaders) {
	t.Helper()
	if got := h.Get(headerMemoriesInjected); got != want.memories {
		t.Fatalf("%s=%q want %q", headerMemoriesInjected, got, want.memories)
	}
	if got := h.Get(headerContextTokens); got != want.tokens {
		t.Fatalf("%s=%q want %q", headerContextTokens, got, want.tokens)
	}
	if got := h.Get(headerContextFallback); got != want.fallback {
		t.Fatalf("%s=%q want %q", headerContextFallback, got, want.fallback)
	}
}

func assertDirectiveOnly(t *testing.T, msgs []provider.Message) {
	t.Helper()
	if len(msgs) != 2 || msgs[0].Content != "org directive" || msgs[1].Content != "hi" {
		t.Fatalf("messages=%+v", msgs)
	}
}

func assertPhase2ProviderMessages(t *testing.T, msgs []provider.Message) {
	t.Helper()
	if len(msgs) != 3 {
		t.Fatalf("messages=%+v", msgs)
	}
	if msgs[0].Content != "client system" || msgs[2].Content != "hello" {
		t.Fatalf("history=%+v", msgs)
	}
	if msgs[1].Role != "system" || msgs[1].Content != "org directive" {
		t.Fatalf("directive=%+v", msgs[1])
	}
}

func runApplyInjection(t *testing.T, h chatCompletionHandler, msgs []provider.Message) messageInjectionOutcome {
	t.Helper()
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	return h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", msgs)
}

func runForwardChat(t *testing.T, h chatCompletionHandler, stream bool, skipMemory bool) (*httptest.ResponseRecorder, provider.Request) {
	t.Helper()
	return runForwardChatTo(t, h, stream, skipMemory, &captureLLMProvider{})
}

func runForwardChatTo(
	t *testing.T,
	h chatCompletionHandler,
	stream bool,
	skipMemory bool,
	prov provider.Provider,
) (*httptest.ResponseRecorder, provider.Request) {
	t.Helper()
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Stream: stream, Messages: baseChatMessages()}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	if skipMemory {
		req.Header.Set(validation.HeaderSkipMemory, "true")
	}
	var w http.ResponseWriter
	rec := httptest.NewRecorder()
	w = rec
	if stream {
		fr := newFlushRecorder()
		w = fr
		rec = fr.ResponseRecorder
	}
	h.forwardChatCompletion(chatForwardParams{w: w, r: req, parsed: parsed, prov: prov})
	switch c := prov.(type) {
	case *captureLLMProvider:
		return rec, c.last
	case *captureStreamingProvider:
		return rec, c.last
	case *failingLLMProvider:
		return rec, c.last
	default:
		return rec, provider.Request{}
	}
}

func TestUnit_ApplyContextOrDirective_DisabledNoAssembleCall(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "should-not-inject"}}
	out := runApplyInjection(t, contextHandler(false, fake), []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	assertDirectiveOnly(t, out.Messages)
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when disabled")
	}
}

func TestUnit_ApplyContextOrDirective_NilClientNoAssembleCall(t *testing.T) {
	t.Parallel()
	out := runApplyInjection(t, contextHandler(true, nil), []provider.Message{{Role: "user", Content: "hi"}})
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when client nil")
	}
	assertDirectiveOnly(t, out.Messages)
}

func TestUnit_ApplyContextOrDirective_SkipMemoryNoAssembleCall(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	h := contextHandler(true, fake)
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	req.Header.Set(validation.HeaderSkipMemory, "true")
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false on Skip-Memory")
	}
}

func TestUnit_ApplyContextOrDirective_FallbackKeepsDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		Fallback: true, FallbackReason: "DeadlineExceeded",
	}}
	out := runApplyInjection(t, contextHandler(true, fake), []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 1 {
		t.Fatalf("Assemble calls=%d want 1", fake.calls.Load())
	}
	if !out.Meta.Attempted || !out.Meta.Fallback {
		t.Fatalf("meta=%+v", out.Meta)
	}
	assertDirectiveOnly(t, out.Messages)
}

func TestUnit_ApplyContextOrDirective_SuccessInjectsAdditive(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 42, MemoriesIncluded: 3,
	}}
	msgs := []provider.Message{
		{Role: "system", Content: "client system"},
		{Role: "user", Content: "hello"},
	}
	out := runApplyInjection(t, contextHandler(true, fake), msgs)
	assertSuccessAssembleInjection(t, fake, out)
}

func assertSuccessAssembleInjection(t *testing.T, fake *fakeContextAssembler, out messageInjectionOutcome) {
	t.Helper()
	if fake.calls.Load() != 1 {
		t.Fatalf("Assemble calls=%d", fake.calls.Load())
	}
	if fake.lastReq.Query != "hello" || fake.lastReq.OrgID != testChatOrgID {
		t.Fatalf("params=%+v", fake.lastReq)
	}
	if len(out.Messages) != 3 || out.Messages[0].Content != "assembled blob" {
		t.Fatalf("messages=%+v", out.Messages)
	}
	if out.Messages[1].Content != "client system" || out.Messages[2].Content != "hello" {
		t.Fatalf("history altered: %+v", out.Messages)
	}
	if out.Meta.MemoriesInjected != 3 || out.Meta.ContextTokens != 42 || out.Meta.Fallback {
		t.Fatalf("meta=%+v", out.Meta)
	}
}

func TestUnit_ForwardChat_ContextDisabled_Phase2Regression(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	rec, last := runForwardChat(t, contextHandler(false, fake), false, false)
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	assertPhase2ProviderMessages(t, last.Messages)
	assertNoContextHeaders(t, rec.Header())
}

func TestUnit_ForwardChat_NilClient_Phase2Regression(t *testing.T) {
	t.Parallel()
	rec, last := runForwardChat(t, contextHandler(true, nil), false, false)
	assertPhase2ProviderMessages(t, last.Messages)
	assertNoContextHeaders(t, rec.Header())
}

func TestUnit_ForwardChat_AssembleSuccess_HeadersAndMessages(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 11, MemoriesIncluded: 2,
	}}
	rec, last := runForwardChat(t, contextHandler(true, fake), false, false)
	if len(last.Messages) != 3 || last.Messages[0].Content != "assembled blob" {
		t.Fatalf("messages=%+v", last.Messages)
	}
	if last.Messages[1].Content != "client system" || last.Messages[2].Content != "hello" {
		t.Fatalf("history=%+v", last.Messages)
	}
	assertContextHeaders(t, rec.Header(), wantContextHeaders{memories: "2", tokens: "11", fallback: "false"})
}

func TestUnit_ForwardChat_AssembleFallback_HeadersAndDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{Fallback: true}}
	rec, last := runForwardChat(t, contextHandler(true, fake), false, false)
	assertPhase2ProviderMessages(t, last.Messages)
	assertContextHeaders(t, rec.Header(), wantContextHeaders{memories: "0", tokens: "0", fallback: "true"})
}

func TestUnit_ForwardChat_ProviderFailure_EmitsAssembleHeaders(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled", TokensUsed: 5, MemoriesIncluded: 1,
	}}
	fail := &failingLLMProvider{err: &provider.ProviderError{
		ProviderName: "fail", StatusCode: http.StatusBadGateway, ProviderErrMsg: "upstream",
	}}
	rec, _ := runForwardChatTo(t, contextHandler(true, fake), false, false, fail)
	if rec.Code < 400 {
		t.Fatalf("status=%d want error", rec.Code)
	}
	assertContextHeaders(t, rec.Header(), wantContextHeaders{memories: "1", tokens: "5", fallback: "false"})
}

func TestUnit_ForwardChat_ProviderFailure_OmitsHeadersWhenNotAttempted(t *testing.T) {
	t.Parallel()
	fail := &failingLLMProvider{err: &provider.ProviderError{
		ProviderName: "fail", StatusCode: http.StatusBadGateway, ProviderErrMsg: "upstream",
	}}
	rec, _ := runForwardChatTo(t, contextHandler(false, nil), false, false, fail)
	assertNoContextHeaders(t, rec.Header())
}

type streamAssembleCase struct {
	name          string
	enabled       bool
	client        contextAssembler
	skipMemory    bool
	wantAssemble  int32
	wantMsgsFirst string
	wantNoHeaders bool
	want          wantContextHeaders
}

func streamAssembleCases() []streamAssembleCase {
	return []streamAssembleCase{
		{
			name: "disabled", enabled: false,
			client:        &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "x"}},
			wantMsgsFirst: "client system", wantNoHeaders: true,
		},
		{
			name: "nil client", enabled: true, client: nil,
			wantMsgsFirst: "client system", wantNoHeaders: true,
		},
		{
			name: "skip memory", enabled: true, skipMemory: true,
			client:        &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "x"}},
			wantMsgsFirst: "client system", wantNoHeaders: true,
		},
		{
			name: "fallback", enabled: true,
			client:       &fakeContextAssembler{result: contextclient.AssembleResult{Fallback: true}},
			wantAssemble: 1, wantMsgsFirst: "client system",
			want: wantContextHeaders{memories: "0", tokens: "0", fallback: "true"},
		},
		{
			name: "success", enabled: true,
			client: &fakeContextAssembler{result: contextclient.AssembleResult{
				AssembledContext: "assembled blob", TokensUsed: 7, MemoriesIncluded: 1,
			}},
			wantAssemble: 1, wantMsgsFirst: "assembled blob",
			want: wantContextHeaders{memories: "1", tokens: "7", fallback: "false"},
		},
	}
}

func TestUnit_ForwardChat_Streaming_AssembleHeaders(t *testing.T) {
	t.Parallel()
	for _, tc := range streamAssembleCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runStreamAssembleCase(t, tc)
		})
	}
}

func runStreamAssembleCase(t *testing.T, tc streamAssembleCase) {
	t.Helper()
	cap := &captureStreamingProvider{}
	rec, last := runForwardChatTo(t, contextHandler(tc.enabled, tc.client), true, tc.skipMemory, cap)
	var calls int32
	if fake, ok := tc.client.(*fakeContextAssembler); ok {
		calls = fake.calls.Load()
	}
	if calls != tc.wantAssemble {
		t.Fatalf("Assemble calls=%d want %d", calls, tc.wantAssemble)
	}
	if len(last.Messages) < 1 || last.Messages[0].Content != tc.wantMsgsFirst {
		t.Fatalf("messages=%+v want first %q", last.Messages, tc.wantMsgsFirst)
	}
	if tc.wantNoHeaders {
		assertNoContextHeaders(t, rec.Header())
		return
	}
	assertContextHeaders(t, rec.Header(), tc.want)
}

type captureStreamingProvider struct {
	last provider.Request
}

func (c *captureStreamingProvider) Complete(_ context.Context, req provider.Request) (provider.Response, error) {
	c.last = req
	body := "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\ndata: [DONE]\n\n"
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(body)),
	}, nil
}

func (c *captureStreamingProvider) Name() string { return "capture-stream" }

func (c *captureStreamingProvider) SupportedModels() []string { return []string{"gpt-4o"} }

type failingLLMProvider struct {
	last provider.Request
	err  error
}

func (f *failingLLMProvider) Complete(_ context.Context, req provider.Request) (provider.Response, error) {
	f.last = req
	if f.err != nil {
		return provider.Response{}, f.err
	}
	return provider.Response{}, errors.New("provider failed")
}

func (f *failingLLMProvider) Name() string { return "fail" }

func (f *failingLLMProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func TestUnit_SetContextAssembleResponseHeaders_OmitWhenNotAttempted(t *testing.T) {
	t.Parallel()
	rec := httptest.NewRecorder()
	setContextAssembleResponseHeaders(rec, context.Background())
	assertNoContextHeaders(t, rec.Header())
	ctx := withContextAssembleMeta(context.Background(), contextAssembleMeta{})
	setContextAssembleResponseHeaders(rec, ctx)
	assertNoContextHeaders(t, rec.Header())
}

func TestUnit_AssembleParamsFromRequest_MissingTenant(t *testing.T) {
	t.Parallel()
	_, ok := assembleParamsFromRequest(context.Background(), "gpt-4o", nil)
	if ok {
		t.Fatal("expected ok=false without tenant context")
	}
}

func TestUnit_LastUserQuery_EmptyWhenNoUser(t *testing.T) {
	t.Parallel()
	if got := lastUserQuery([]provider.Message{{Role: "system", Content: "sys"}}); got != "" {
		t.Fatalf("got %q want empty", got)
	}
}

func TestUnit_ApplyContextOrDirective_EmptyAssembledUsesDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "   ", TokensUsed: 1,
	}}
	out := runApplyInjection(t, contextHandler(true, fake), []provider.Message{{Role: "user", Content: "hi"}})
	if !out.Meta.Attempted || out.Meta.Fallback {
		t.Fatalf("meta=%+v", out.Meta)
	}
	assertDirectiveOnly(t, out.Messages)
}

func TestUnit_ApplyContextOrDirective_MissingTenantFallsBackToDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	h := contextHandler(true, fake)
	ctx := directiveCtx(context.Background())
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when tenant IDs missing")
	}
	assertDirectiveOnly(t, out.Messages)
}
