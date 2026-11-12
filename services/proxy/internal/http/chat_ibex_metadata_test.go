package http

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
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
	// Request start is stashed 25ms back so proxy_overhead_ms is non-zero.
	rec := forwardTimed(t, h, false)
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

// TestUnit_ProxyOverheadMs_SubtractsProvider guards the one arithmetic property
// the proxy-overhead SLO depends on: provider time is excluded from the value.
// The ratified objective is p99 ≤20 ms of enforcement overhead and the SLI
// "excludes provider time" (engineering/architecture-v2/05-request-lifecycle-and-slos.md
// §budget, ADR-0034:59). So when provider time dominates the request, a correct
// proxyOverheadMs must report well under 20 ms; a regression that stopped
// subtracting provider time would report the whole ~100 ms wall time and fail.
// The small-provider case pins the other direction: the subtraction must not
// invert or over-subtract, which would report a near-zero overhead for a request
// that really spent its time in the proxy.
func TestUnit_ProxyOverheadMs_SubtractsProvider(t *testing.T) {
	t.Parallel()
	// sloOverheadMs is the ratified p99 ceiling; a single deterministic case has
	// to hold the same bound the histogram is alerting on.
	const (
		requestAgeMs  = 100 // start is this far in the past
		sloOverheadMs = 20
	)
	tests := []struct {
		name       string
		providerMs int64
		minMs      int64
		maxMs      int64 // exclusive
	}{
		{
			// Wall ~100 ms, provider 95 ms => ~5 ms of real overhead. Without the
			// subtraction this is ~100 ms, which the SLO bound rejects.
			name:       "provider_dominates_wall_time",
			providerMs: 95,
			minMs:      0,
			maxMs:      sloOverheadMs,
		},
		{
			// Wall ~100 ms, provider 5 ms => ~95 ms of real overhead. Catches an
			// over-subtraction (subtracting twice, or subtracting wall instead of
			// provider) that would hide a real SLO breach.
			name:       "provider_small_keeps_arithmetic_honest",
			providerMs: 5,
			minMs:      3 * sloOverheadMs,
			maxMs:      2 * requestAgeMs,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			start := time.Now().Add(-requestAgeMs * time.Millisecond)
			ctx := WithRequestStart(context.Background(), start)
			ctx = withProviderDurationMs(ctx, tc.providerMs)
			got := proxyOverheadMs(ctx)
			t.Logf("wall≈%dms provider=%dms overhead=%dms want [%d,%d)",
				requestAgeMs, tc.providerMs, got, tc.minMs, tc.maxMs)
			if got < tc.minMs || got >= tc.maxMs {
				t.Fatalf("proxy_overhead_ms=%d want in [%d,%d) for provider=%dms over ~%dms wall",
					got, tc.minMs, tc.maxMs, tc.providerMs, requestAgeMs)
			}
		})
	}
}
