package http

import (
	"context"
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

func assertNoContextHeaders(t *testing.T, h http.Header) {
	t.Helper()
	for _, name := range []string{headerMemoriesInjected, headerContextTokens, headerContextFallback} {
		if got := h.Get(name); got != "" {
			t.Fatalf("%s=%q want omitted", name, got)
		}
	}
}

func assertContextHeaders(t *testing.T, h http.Header, memories, tokens, fallback string) {
	t.Helper()
	if got := h.Get(headerMemoriesInjected); got != memories {
		t.Fatalf("%s=%q want %q", headerMemoriesInjected, got, memories)
	}
	if got := h.Get(headerContextTokens); got != tokens {
		t.Fatalf("%s=%q want %q", headerContextTokens, got, tokens)
	}
	if got := h.Get(headerContextFallback); got != fallback {
		t.Fatalf("%s=%q want %q", headerContextFallback, got, fallback)
	}
}

func TestUnit_ApplyContextOrDirective_DisabledNoAssembleCall(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "should-not-inject"}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: false, contextClient: fake,
	}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	msgs := []provider.Message{{Role: "user", Content: "hi"}}
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", msgs)
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	if len(out.Messages) != 2 || out.Messages[1].Content != "hi" {
		t.Fatalf("messages=%+v", out.Messages)
	}
	if out.Messages[0].Content != "org directive" {
		t.Fatalf("directive=%+v", out.Messages[0])
	}
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when disabled")
	}
}

func TestUnit_ApplyContextOrDirective_NilClientNoAssembleCall(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{log: logger.Discard("proxy"), contextEnabled: true, contextClient: nil}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	msgs := []provider.Message{{Role: "user", Content: "hi"}}
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", msgs)
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when client nil")
	}
	if len(out.Messages) != 2 || out.Messages[0].Content != "org directive" {
		t.Fatalf("messages=%+v", out.Messages)
	}
}

func TestUnit_ApplyContextOrDirective_SkipMemoryNoAssembleCall(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
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
		Fallback: true, FallbackReason: "DeadlineExceeded", TokensUsed: 0,
	}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	msgs := []provider.Message{{Role: "user", Content: "hi"}}
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", msgs)
	if fake.calls.Load() != 1 {
		t.Fatalf("Assemble calls=%d want 1", fake.calls.Load())
	}
	if !out.Meta.Attempted || !out.Meta.Fallback {
		t.Fatalf("meta=%+v", out.Meta)
	}
	if len(out.Messages) != 2 || out.Messages[0].Content != "org directive" {
		t.Fatalf("messages=%+v", out.Messages)
	}
}

func TestUnit_ApplyContextOrDirective_SuccessInjectsAdditive(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 42, MemoriesIncluded: 3,
	}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	msgs := []provider.Message{
		{Role: "system", Content: "client system"},
		{Role: "user", Content: "hello"},
	}
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", msgs)
	if fake.calls.Load() != 1 {
		t.Fatalf("Assemble calls=%d", fake.calls.Load())
	}
	if fake.lastReq.Query != "hello" || fake.lastReq.OrgID != testChatOrgID {
		t.Fatalf("params=%+v", fake.lastReq)
	}
	if len(out.Messages) != 3 {
		t.Fatalf("len=%d messages=%+v", len(out.Messages), out.Messages)
	}
	if out.Messages[0].Role != "system" || out.Messages[0].Content != "assembled blob" {
		t.Fatalf("first=%+v", out.Messages[0])
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
	cap := &captureLLMProvider{}
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Messages: baseChatMessages()}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: false, contextClient: fake,
	}
	h.forwardChatCompletion(chatForwardParams{w: rec, r: req, parsed: parsed, prov: cap})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	assertPhase2ProviderMessages(t, cap.last.Messages)
	assertNoContextHeaders(t, rec.Header())
}

func TestUnit_ForwardChat_NilClient_Phase2Regression(t *testing.T) {
	t.Parallel()
	cap := &captureLLMProvider{}
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Messages: baseChatMessages()}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{log: logger.Discard("proxy"), contextEnabled: true}
	h.forwardChatCompletion(chatForwardParams{w: rec, r: req, parsed: parsed, prov: cap})
	assertPhase2ProviderMessages(t, cap.last.Messages)
	assertNoContextHeaders(t, rec.Header())
}

func assertPhase2ProviderMessages(t *testing.T, msgs []provider.Message) {
	t.Helper()
	// Matches TestUnit_ForwardChatCompletion_InjectsBeforeComplete (system_append).
	if len(msgs) != 3 {
		t.Fatalf("messages=%+v", msgs)
	}
	if msgs[0].Content != "client system" {
		t.Fatalf("first=%+v", msgs[0])
	}
	if msgs[1].Role != "system" || msgs[1].Content != "org directive" {
		t.Fatalf("directive=%+v", msgs[1])
	}
	if msgs[2].Content != "hello" {
		t.Fatalf("user=%+v", msgs[2])
	}
}

func TestUnit_ForwardChat_AssembleSuccess_HeadersAndMessages(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 11, MemoriesIncluded: 2,
	}}
	cap := &captureLLMProvider{}
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Messages: baseChatMessages()}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
	h.forwardChatCompletion(chatForwardParams{w: rec, r: req, parsed: parsed, prov: cap})
	if len(cap.last.Messages) != 3 {
		t.Fatalf("messages=%+v", cap.last.Messages)
	}
	if cap.last.Messages[0].Content != "assembled blob" {
		t.Fatalf("first=%+v", cap.last.Messages[0])
	}
	if cap.last.Messages[1].Content != "client system" || cap.last.Messages[2].Content != "hello" {
		t.Fatalf("history=%+v", cap.last.Messages)
	}
	assertContextHeaders(t, rec.Header(), "2", "11", "false")
}

func TestUnit_ForwardChat_AssembleFallback_HeadersAndDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{Fallback: true}}
	cap := &captureLLMProvider{}
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Messages: baseChatMessages()}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
	h.forwardChatCompletion(chatForwardParams{w: rec, r: req, parsed: parsed, prov: cap})
	assertPhase2ProviderMessages(t, cap.last.Messages)
	assertContextHeaders(t, rec.Header(), "0", "0", "true")
}

func TestUnit_ForwardChat_Streaming_AssembleHeaders(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name          string
		enabled       bool
		client        contextAssembler
		skipMemory    bool
		wantAssemble  int32
		wantMsgsFirst string
		wantNoHeaders bool
		wantMemories  string
		wantTokens    string
		wantFallback  string
	}{
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
			wantMemories: "0", wantTokens: "0", wantFallback: "true",
		},
		{
			name: "success", enabled: true,
			client: &fakeContextAssembler{result: contextclient.AssembleResult{
				AssembledContext: "assembled blob", TokensUsed: 7, MemoriesIncluded: 1,
			}},
			wantAssemble: 1, wantMsgsFirst: "assembled blob",
			wantMemories: "1", wantTokens: "7", wantFallback: "false",
		},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			cap := &captureStreamingProvider{}
			parsed := &llm.ChatCompletionRequest{
				Model: "gpt-4o", Stream: true, Messages: baseChatMessages(),
			}
			ctx := directiveCtx(contextTestAuthCtx(t))
			req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
			if tc.skipMemory {
				req.Header.Set(validation.HeaderSkipMemory, "true")
			}
			rec := newFlushRecorder()
			h := chatCompletionHandler{
				log: logger.Discard("proxy"), contextEnabled: tc.enabled, contextClient: tc.client,
			}
			h.forwardChatCompletion(chatForwardParams{w: rec, r: req, parsed: parsed, prov: cap})
			var calls int32
			if fake, ok := tc.client.(*fakeContextAssembler); ok {
				calls = fake.calls.Load()
			}
			if calls != tc.wantAssemble {
				t.Fatalf("Assemble calls=%d want %d", calls, tc.wantAssemble)
			}
			if len(cap.last.Messages) < 1 || cap.last.Messages[0].Content != tc.wantMsgsFirst {
				t.Fatalf("messages=%+v want first %q", cap.last.Messages, tc.wantMsgsFirst)
			}
			if tc.wantNoHeaders {
				assertNoContextHeaders(t, rec.Header())
				return
			}
			assertContextHeaders(t, rec.Header(), tc.wantMemories, tc.wantTokens, tc.wantFallback)
		})
	}
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
		AssembledContext: "   ", TokensUsed: 1, MemoriesIncluded: 0,
	}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", []provider.Message{{Role: "user", Content: "hi"}})
	if !out.Meta.Attempted || out.Meta.Fallback {
		t.Fatalf("meta=%+v", out.Meta)
	}
	if len(out.Messages) != 2 || out.Messages[0].Content != "org directive" {
		t.Fatalf("messages=%+v", out.Messages)
	}
}

func TestUnit_ApplyContextOrDirective_MissingTenantFallsBackToDirective(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	h := chatCompletionHandler{
		log: logger.Discard("proxy"), contextEnabled: true, contextClient: fake,
	}
	ctx := directiveCtx(context.Background()) // no auth/agent
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	out := h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", []provider.Message{{Role: "user", Content: "hi"}})
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	if out.Meta.Attempted {
		t.Fatal("Attempted should be false when tenant IDs missing")
	}
	if len(out.Messages) != 2 || out.Messages[0].Content != "org directive" {
		t.Fatalf("messages=%+v", out.Messages)
	}
}
