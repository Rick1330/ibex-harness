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
	// Request start is stashed 100 ms back so proxy_overhead_ms is non-zero.
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

// TestUnit_ProxyOverheadMs_NoRequestStart covers the one degenerate input the
// diagnostic field can see: a context with no request-start value reports 0
// rather than a bogus elapsed time.
func TestUnit_ProxyOverheadMs_NoRequestStart(t *testing.T) {
	t.Parallel()
	if got := proxyOverheadMs(context.Background()); got != 0 {
		t.Fatalf("proxy_overhead_ms=%d want 0 without a request start", got)
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

// TestUnit_ProxyOverhead_SubtractsProvider guards the one arithmetic property
// the proxy-overhead SLO depends on: provider time is subtracted from the sample
// exactly once, at full duration precision. The ratified objective is p99 ≤20 ms
// of enforcement overhead and the SLI "excludes provider time"
// (engineering/architecture-v2/05-request-lifecycle-and-slos.md §budget,
// ADR-0034:59).
//
// Every case is duration-based — the request start and the "now" it is compared
// against are both fixed, so the assertions are exact instead of racing the wall
// clock. The provider-dominates case fails if provider time is not subtracted
// (it would report the whole 100 ms wall time); the small-provider case fails if
// the subtraction is inverted or over-applied; the mixed case fails if the
// provider leg is subtracted twice (40 ms twice over 100 ms lands on exactly
// 20 ms, the objective, hiding a 60 ms breach).
func TestUnit_ProxyOverhead_SubtractsProvider(t *testing.T) {
	t.Parallel()
	const (
		requestAge  = 100 * time.Millisecond
		sloOverhead = 20 * time.Millisecond
	)
	start := time.Date(2026, time.November, 12, 9, 0, 0, 0, time.UTC)
	tests := []struct {
		name         string
		provider     time.Duration
		hasProvider  bool
		want         time.Duration
		wantBelowSLO bool
	}{
		{
			// Wall 100 ms, provider 95 ms => 5 ms of real overhead. Without the
			// subtraction this is 100 ms, which the SLO bound rejects.
			name:         "provider_dominates_wall_time",
			provider:     95 * time.Millisecond,
			hasProvider:  true,
			want:         5 * time.Millisecond,
			wantBelowSLO: true,
		},
		{
			// Wall 100 ms, provider 5 ms => 95 ms of real overhead. Catches an
			// over-subtraction (subtracting twice, or subtracting wall instead of
			// provider) that would hide a real SLO breach.
			name:        "provider_small_keeps_arithmetic_honest",
			provider:    5 * time.Millisecond,
			hasProvider: true,
			want:        95 * time.Millisecond,
		},
		{
			// Wall 100 ms, provider 40 ms => 60 ms. A double subtraction yields
			// 20 ms — compliant by exactly the objective — so the exact value is
			// the assertion, not a range.
			name:        "mixed_duration_subtracts_exactly_once",
			provider:    40 * time.Millisecond,
			hasProvider: true,
			want:        60 * time.Millisecond,
		},
		{
			name:        "provider_longer_than_wall_clamps_to_zero",
			provider:    120 * time.Millisecond,
			hasProvider: true,
			want:        0,
		},
		{
			name: "no_provider_measurement_keeps_wall_time",
			want: requestAge,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			ctx := WithRequestStart(context.Background(), start)
			if tc.hasProvider {
				ctx = withProviderDurationMs(ctx, tc.provider.Milliseconds())
			}
			got, ok := proxyOverheadDuration(ctx, start.Add(requestAge))
			t.Logf("wall=%v provider=%v (measured=%t) overhead=%v (ms view %d) want %v",
				requestAge, tc.provider, tc.hasProvider, got, got.Milliseconds(), tc.want)
			if !ok {
				t.Fatalf("proxyOverheadDuration reported no sample; want %v", tc.want)
			}
			if got != tc.want {
				t.Fatalf("proxy overhead=%v want %v (provider=%v over %v wall)",
					got, tc.want, tc.provider, requestAge)
			}
			// The embedded proxy_overhead_ms is the truncating view of the same
			// arithmetic: it may round down, it must never round up or differ.
			if ms := got.Milliseconds(); ms != tc.want.Milliseconds() {
				t.Fatalf("proxy_overhead_ms=%d want %d", ms, tc.want.Milliseconds())
			}
			if tc.wantBelowSLO && got >= sloOverhead {
				t.Fatalf("provider-dominated request must stay under the %v objective, got %v", sloOverhead, got)
			}
		})
	}
}
