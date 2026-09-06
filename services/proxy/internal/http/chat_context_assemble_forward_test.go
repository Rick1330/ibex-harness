package http

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

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
	assertAssembledMessages(t, last.Messages)
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
	rec, _ := runForwardChatTo(t, forwardChatOpts{
		h: contextHandler(true, fake), prov: fail,
	})
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
	rec, _ := runForwardChatTo(t, forwardChatOpts{
		h: contextHandler(false, nil), prov: fail,
	})
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
	rec, last := runForwardChatTo(t, forwardChatOpts{
		h: contextHandler(tc.enabled, tc.client), stream: true, skipMemory: tc.skipMemory, prov: cap,
	})
	assertStreamAssembleCalls(t, tc, last, rec)
}

func assertStreamAssembleCalls(t *testing.T, tc streamAssembleCase, last provider.Request, rec *httptest.ResponseRecorder) {
	t.Helper()
	calls := assembleCallCount(tc.client)
	if calls != tc.wantAssemble {
		t.Fatalf("Assemble calls=%d want %d", calls, tc.wantAssemble)
	}
	if len(last.Messages) < 1 {
		t.Fatalf("messages=%+v", last.Messages)
	}
	if last.Messages[0].Content != tc.wantMsgsFirst {
		t.Fatalf("first=%q want %q", last.Messages[0].Content, tc.wantMsgsFirst)
	}
	if tc.wantNoHeaders {
		assertNoContextHeaders(t, rec.Header())
		return
	}
	assertContextHeaders(t, rec.Header(), tc.want)
}

func assembleCallCount(client contextAssembler) int32 {
	fake, ok := client.(*fakeContextAssembler)
	if !ok {
		return 0
	}
	return fake.calls.Load()
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

func TestUnit_ForwardChat_EmptyAssembled_FallbackHeaderAndMetric(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "", TokensUsed: 0, MemoriesIncluded: 0,
	}}
	reg := metrics.NewProxy("empty-assemble-forward-test")
	h := contextHandler(true, fake)
	h.metrics = reg
	rec, last := runForwardChat(t, h, false, false)
	assertPhase2ProviderMessages(t, last.Messages)
	assertContextHeaders(t, rec.Header(), wantContextHeaders{
		memories: "0", tokens: "0", fallback: "true",
	})
	assertAssembleFallbackMetric(t, reg, emptyAssembleFallbackReason, 1)
}
