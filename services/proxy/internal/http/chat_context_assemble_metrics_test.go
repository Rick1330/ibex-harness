package http

import (
	"context"
	"math"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/responsepipeline"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	dto "github.com/prometheus/client_model/go"
)

// TestUnit_ForwardChat_RecordsProxyOverheadSeconds drives the assemble path with
// a real ProxyRegistry and reads the histogram back from it. The observed sample
// must equal the proxy_overhead_ms the response carries, because both come from
// the same proxyOverheadMs evaluation.
func TestUnit_ForwardChat_RecordsProxyOverheadSeconds(t *testing.T) {
	t.Parallel()
	reg := metrics.NewProxy("proxy-overhead-http-test")
	h := embedMetadataHandler(&fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 11, MemoriesIncluded: 2,
	}})
	h.metrics = reg
	rec := forwardTimed(t, h, false)

	reported := ibexOverheadMsFromBody(t, rec.Body.String())
	hist := histogramByName(t, reg, "ibex_proxy_overhead_seconds")
	if got := hist.GetSampleCount(); got != 1 {
		t.Fatalf("ibex_proxy_overhead_seconds samples=%d want 1", got)
	}
	observedSeconds := hist.GetSampleSum()
	t.Logf("proxy_overhead_ms=%d observed=%vs buckets=%d", reported, observedSeconds, len(hist.GetBucket()))
	if math.Abs(observedSeconds-float64(reported)/1000) > 1e-9 {
		t.Fatalf("histogram sum=%vs want proxy_overhead_ms=%d", observedSeconds, reported)
	}
	if observedSeconds <= 0 {
		t.Fatalf("expected a positive overhead sample, got %vs", observedSeconds)
	}
}

// TestUnit_ForwardChat_SkipMemory_RecordsOverheadWithoutMetadata pins the
// coverage decision: a request that skips Assemble writes no ibex block and no
// X-IBEX-Context-* headers, but still contributes an overhead sample — otherwise
// the SLO p99 would be computed over context-enabled traffic only.
func TestUnit_ForwardChat_SkipMemory_RecordsOverheadWithoutMetadata(t *testing.T) {
	t.Parallel()
	reg := metrics.NewProxy("proxy-overhead-skip-memory-test")
	h := embedMetadataHandler(&fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob",
	}})
	h.metrics = reg
	rec := forwardTimed(t, h, true)

	assertNoContextHeaders(t, rec.Header())
	if strings.Contains(rec.Body.String(), `"ibex"`) {
		t.Fatal("ibex block must be omitted when Assemble was not attempted")
	}
	hist := histogramByName(t, reg, "ibex_proxy_overhead_seconds")
	if got := hist.GetSampleCount(); got != 1 {
		t.Fatalf("ibex_proxy_overhead_seconds samples=%d want 1", got)
	}
	if sum := hist.GetSampleSum(); sum <= 0 {
		t.Fatalf("expected a positive overhead sample, got %vs", sum)
	}
}

// TestUnit_ApplyContextOrDirective_RecordsAssembleSeconds covers every way an
// Assemble call can return: a fail-open timeout is exactly what the
// context-assembly SLO panel has to show, so it must be observed too.
func TestUnit_ApplyContextOrDirective_RecordsAssembleSeconds(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		result contextclient.AssembleResult
	}{
		{name: "success", result: contextclient.AssembleResult{AssembledContext: "assembled"}},
		{name: "grpc_fallback", result: contextclient.AssembleResult{Fallback: true, FallbackReason: "DeadlineExceeded"}},
		{name: "empty", result: contextclient.AssembleResult{AssembledContext: "   "}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			reg := metrics.NewProxy("assemble-seconds-" + tc.name)
			h := contextHandler(true, &fakeContextAssembler{result: tc.result})
			h.metrics = reg
			_ = runApplyInjection(t, h, []provider.Message{{Role: "user", Content: "hi"}})

			hist := histogramByName(t, reg, "ibex_proxy_context_assemble_seconds")
			if got := hist.GetSampleCount(); got != 1 {
				t.Fatalf("ibex_proxy_context_assemble_seconds samples=%d want 1", got)
			}
			if sum := hist.GetSampleSum(); sum < 0 {
				t.Fatalf("assemble duration=%vs must be non-negative", sum)
			}
			t.Logf("assemble seconds observed=%vs fallback=%t", hist.GetSampleSum(), tc.result.Fallback)
		})
	}
}

// TestUnit_ApplyContextOrDirective_NilMetricsDoesNotPanic keeps the recorder
// wiring optional: unit handlers built by contextHandler have no registry.
func TestUnit_ApplyContextOrDirective_NilMetricsDoesNotPanic(t *testing.T) {
	t.Parallel()
	h := contextHandler(true, &fakeContextAssembler{result: contextclient.AssembleResult{AssembledContext: "x"}})
	if h.metrics != nil {
		t.Fatal("contextHandler must not wire metrics")
	}
	out := runApplyInjection(t, h, []provider.Message{{Role: "user", Content: "hi"}})
	if out.Meta.overhead != nil {
		t.Fatal("nil registry must store a nil recorder, not a typed nil")
	}
}

func embedMetadataHandler(fake *fakeContextAssembler) chatCompletionHandler {
	h := contextHandler(true, fake)
	h.responsePipeline = responsepipeline.NewPipeline([]responsepipeline.Stage{
		responsepipeline.IBEXMetadataStage{},
	})
	return h
}

// forwardTimed runs the non-streaming forward path with a request-start time in
// context so proxy_overhead_ms — and therefore the histogram sample — is non-zero.
func forwardTimed(t *testing.T, h chatCompletionHandler, skipMemory bool) *httptest.ResponseRecorder {
	t.Helper()
	parsed := &llm.ChatCompletionRequest{Model: "gpt-4o", Messages: baseChatMessages()}
	ctx := WithRequestStart(directiveCtx(contextTestAuthCtx(t)), time.Now().Add(-100*time.Millisecond))
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	if skipMemory {
		req.Header.Set(validation.HeaderSkipMemory, "true")
	}
	rec := httptest.NewRecorder()
	h.forwardChatCompletion(chatForwardParams{w: rec, r: req, parsed: parsed, prov: &captureLLMProvider{}})
	return rec
}

func ibexOverheadMsFromBody(t *testing.T, body string) int64 {
	t.Helper()
	const key = `"proxy_overhead_ms":`
	start := strings.Index(body, key)
	if start < 0 {
		t.Fatalf("missing proxy_overhead_ms in body: %s", body)
	}
	rest := body[start+len(key):]
	end := strings.IndexAny(rest, ",}")
	if end < 0 {
		t.Fatalf("unterminated proxy_overhead_ms in body: %s", body)
	}
	ms, err := strconv.ParseInt(strings.TrimSpace(rest[:end]), 10, 64)
	if err != nil {
		t.Fatalf("parse proxy_overhead_ms %q: %v", rest[:end], err)
	}
	return ms
}

func histogramByName(t *testing.T, reg *metrics.ProxyRegistry, name string) *dto.Histogram {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	for _, mf := range mfs {
		if mf.GetName() != name {
			continue
		}
		if len(mf.GetMetric()) != 1 {
			t.Fatalf("%s samples=%d want 1 unlabelled series", name, len(mf.GetMetric()))
		}
		return mf.GetMetric()[0].GetHistogram()
	}
	t.Fatalf("missing %s family", name)
	return nil
}

// BenchmarkAttachIbexMetadataForPipeline isolates the cost of the new
// observation: no_recorder is the pre-change behaviour (the function still
// computes proxyOverheadMs for the ibex block), with_recorder adds exactly the
// histogram Observe.
func BenchmarkAttachIbexMetadataForPipeline(b *testing.B) {
	reg := metrics.NewProxy("bench-ibex-metadata")
	for _, tc := range []struct {
		name     string
		recorder proxyOverheadRecorder
	}{
		{name: "no_recorder"},
		{name: "with_recorder", recorder: reg},
	} {
		b.Run(tc.name, func(b *testing.B) {
			ctx := WithRequestStart(context.Background(), time.Now())
			ctx = withProviderDurationMs(ctx, 1)
			ctx = withContextAssembleMeta(ctx, contextAssembleMeta{Attempted: true, overhead: tc.recorder})
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				_ = attachIbexMetadataForPipeline(ctx)
			}
		})
	}
}
