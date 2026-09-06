package http

import (
	"context"
	"net/http"
	"net/http/httptest"
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
	if len(msgs) != 2 {
		t.Fatalf("messages=%+v", msgs)
	}
	if msgs[0].Content != "org directive" {
		t.Fatalf("directive=%+v", msgs[0])
	}
	if msgs[1].Content != "hi" {
		t.Fatalf("user=%+v", msgs[1])
	}
}

func assertPhase2ProviderMessages(t *testing.T, msgs []provider.Message) {
	t.Helper()
	if len(msgs) != 3 {
		t.Fatalf("messages=%+v", msgs)
	}
	if msgs[0].Content != "client system" {
		t.Fatalf("first=%+v", msgs[0])
	}
	if msgs[2].Content != "hello" {
		t.Fatalf("user=%+v", msgs[2])
	}
	if msgs[1].Role != "system" {
		t.Fatalf("directive role=%+v", msgs[1])
	}
	if msgs[1].Content != "org directive" {
		t.Fatalf("directive=%+v", msgs[1])
	}
}

func runApplyInjection(t *testing.T, h chatCompletionHandler, msgs []provider.Message) messageInjectionOutcome {
	t.Helper()
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	return h.applyContextOrDirectiveInjection(ctx, req, "gpt-4o", msgs)
}

type forwardChatOpts struct {
	h          chatCompletionHandler
	stream     bool
	skipMemory bool
	prov       provider.Provider
}

func runForwardChat(t *testing.T, h chatCompletionHandler, stream bool, skipMemory bool) (*httptest.ResponseRecorder, provider.Request) {
	t.Helper()
	return runForwardChatTo(t, forwardChatOpts{
		h: h, stream: stream, skipMemory: skipMemory, prov: &captureLLMProvider{},
	})
}

func runForwardChatTo(t *testing.T, opts forwardChatOpts) (*httptest.ResponseRecorder, provider.Request) {
	t.Helper()
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Stream: opts.stream, Messages: baseChatMessages()}
	ctx := directiveCtx(contextTestAuthCtx(t))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	if opts.skipMemory {
		req.Header.Set(validation.HeaderSkipMemory, "true")
	}
	rec, w := forwardChatWriter(opts.stream)
	opts.h.forwardChatCompletion(chatForwardParams{w: w, r: req, parsed: parsed, prov: opts.prov})
	return rec, capturedProviderRequest(opts.prov)
}

func forwardChatWriter(stream bool) (*httptest.ResponseRecorder, http.ResponseWriter) {
	rec := httptest.NewRecorder()
	if !stream {
		return rec, rec
	}
	fr := newFlushRecorder()
	return fr.ResponseRecorder, fr
}

func capturedProviderRequest(prov provider.Provider) provider.Request {
	switch c := prov.(type) {
	case *captureLLMProvider:
		return c.last
	case *captureStreamingProvider:
		return c.last
	case *failingLLMProvider:
		return c.last
	default:
		return provider.Request{}
	}
}
