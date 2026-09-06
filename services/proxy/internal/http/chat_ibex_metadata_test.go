package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

func TestUnit_ForwardChat_SkipMemory_OmitsHeaders(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "assembled"}}
	rec, last := runForwardChat(t, contextHandler(true, fake), false, true)
	if fake.calls.Load() != 0 {
		t.Fatalf("Assemble calls=%d want 0", fake.calls.Load())
	}
	assertPhase2ProviderMessages(t, last.Messages)
	assertNoContextHeaders(t, rec.Header())
	if strings.Contains(rec.Body.String(), `"ibex"`) {
		t.Fatal("ibex block must not appear when Assemble was not attempted")
	}
}

func TestUnit_ForwardChat_EmbedMetadata_IncludesIbexBlock(t *testing.T) {
	t.Parallel()
	fake := &fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 11, MemoriesIncluded: 2,
	}}
	h := contextHandler(true, fake)
	h.responsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{
		responsepipeline.IBEXMetadataStage{},
	})
	ctxStart := time.Now().Add(-25 * time.Millisecond)
	// Stash request start via middleware helper so proxy_overhead_ms is non-zero.
	runForwardWithStart := func() *httptest.ResponseRecorder {
		parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Messages: baseChatMessages()}
		ctx := WithRequestStart(directiveCtx(contextTestAuthCtx(t)), ctxStart)
		req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
		rec := httptest.NewRecorder()
		h.forwardChatCompletion(chatForwardParams{
			w: rec, r: req, parsed: parsed, prov: &captureLLMProvider{},
		})
		return rec
	}
	rec := runForwardWithStart()
	assertContextHeaders(t, rec.Header(), wantContextHeaders{memories: "2", tokens: "11", fallback: "false"})
	body := rec.Body.String()
	if !strings.Contains(body, `"ibex"`) {
		t.Fatalf("missing ibex block: %s", body)
	}
	if !strings.Contains(body, `"memories_injected":2`) {
		t.Fatalf("memories_injected missing: %s", body)
	}
	if !strings.Contains(body, `"context_tokens_used":11`) {
		t.Fatalf("context_tokens_used missing: %s", body)
	}
}

func TestUnit_ForwardChat_EmbedPipeline_NoIbexWhenNotAttempted(t *testing.T) {
	t.Parallel()
	h := contextHandler(false, &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "x"}})
	h.responsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{
		responsepipeline.IBEXMetadataStage{},
	})
	rec, _ := runForwardChat(t, h, false, false)
	assertNoContextHeaders(t, rec.Header())
	if strings.Contains(rec.Body.String(), `"ibex"`) {
		t.Fatal("ibex must be omitted when Assemble was not attempted")
	}
}

func TestUnit_AttachIbexMetadataForPipeline_NoopWhenNotAttempted(t *testing.T) {
	t.Parallel()
	ctx := attachIbexMetadataForPipeline(context.Background())
	if _, ok := responsepipeline.IbexMetadataFromContext(ctx); ok {
		t.Fatal("expected no ibex metadata without Attempted")
	}
	ctx = attachIbexMetadataForPipeline(withContextAssembleMeta(context.Background(), contextAssembleMeta{Attempted: false}))
	if _, ok := responsepipeline.IbexMetadataFromContext(ctx); ok {
		t.Fatal("expected no ibex metadata when Attempted=false")
	}
}

func TestUnit_ProxyOverheadMs_SubtractsProvider(t *testing.T) {
	t.Parallel()
	start := time.Now().Add(-100 * time.Millisecond)
	ctx := WithRequestStart(context.Background(), start)
	ctx = withProviderDurationMs(ctx, 40)
	got := proxyOverheadMs(ctx)
	if got < 40 || got > 200 {
		t.Fatalf("proxy_overhead_ms=%d want roughly total-provider", got)
	}
}
