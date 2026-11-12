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
// a real ProxyRegistry and reads both series back. A request that injected
// assembled context is observed on assembly="enabled", and its sample covers the
// response pipeline and JSON serialization, so it is never smaller than the
// pre-pipeline proxy_overhead_ms the body carries.
func TestUnit_ForwardChat_RecordsProxyOverheadSeconds(t *testing.T) {
	t.Parallel()
	reg := metrics.NewProxy("proxy-overhead-http-test")
	h := embedMetadataHandler(&fakeContextAssembler{result: contextclient.AssembleResult{
		AssembledContext: "assembled blob", TokensUsed: 11, MemoriesIncluded: 2,
	}})
	h.metrics = reg
	rec := forwardTimed(t, h, false)

	reported := ibexOverheadMsFromBody(t, rec.Body.String())
	enabled := histogramSeries(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyEnabled))
	if got := enabled.GetSampleCount(); got != 1 {
		t.Fatalf("ibex_proxy_overhead_seconds{assembly=enabled} samples=%d want 1", got)
	}
	observedSeconds := enabled.GetSampleSum()
	t.Logf("proxy_overhead_ms=%d observed=%vs buckets=%d", reported, observedSeconds, len(enabled.GetBucket()))
	// The sample is taken after Run and Bytes, so it must be at least the
	// pre-pipeline metadata value, and it must not run away from it.
	if observedSeconds < float64(reported)/1000 {
		t.Fatalf("histogram sample=%vs is below the pre-pipeline proxy_overhead_ms=%d", observedSeconds, reported)
	}
	if observedSeconds > float64(reported)/1000+0.050 {
		t.Fatalf("histogram sample=%vs is implausibly far above proxy_overhead_ms=%d", observedSeconds, reported)
	}
	if observedSeconds <= 0 {
		t.Fatalf("expected a positive overhead sample, got %vs", observedSeconds)
	}
	// The directive-only population must not absorb injected-context traffic.
	assertHistogramCount(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyDisabled), 0)
	assertAssemblyCounter(t, reg, assemblySeries("ibex_proxy_nonstreaming_requests_total", metrics.ProxyAssemblyEnabled), 1)
	assertAssemblyCounter(t, reg, assemblySeries("ibex_proxy_nonstreaming_requests_total", metrics.ProxyAssemblyDisabled), 0)
}

// TestUnit_ForwardChat_RecordsOverheadWithoutMetadata pins the population
// decision: a request that skips Assemble writes no ibex block and no
// X-IBEX-Context-* headers, but still contributes an overhead sample — labelled
// assembly="disabled", the ratified SLO population — otherwise the p99 would be
// computed over context-enabled traffic only.
func TestUnit_ForwardChat_RecordsOverheadWithoutMetadata(t *testing.T) {
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
	disabled := histogramSeries(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyDisabled))
	if got := disabled.GetSampleCount(); got != 1 {
		t.Fatalf("ibex_proxy_overhead_seconds{assembly=disabled} samples=%d want 1", got)
	}
	if sum := disabled.GetSampleSum(); sum <= 0 {
		t.Fatalf("expected a positive overhead sample, got %vs", sum)
	}
	assertHistogramCount(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyEnabled), 0)
	assertAssemblyCounter(t, reg, assemblySeries("ibex_proxy_nonstreaming_requests_total", metrics.ProxyAssemblyDisabled), 1)
	assertAssemblyCounter(t, reg, assemblySeries("ibex_proxy_nonstreaming_requests_total", metrics.ProxyAssemblyEnabled), 0)
}

// TestUnit_ForwardChat_FailOpenSamplesEnabledPopulation pins where a fail-open
// assembly lands: the RPC ran, so its wall time is inside this request's overhead
// and the request is not in the ratified "context assembly disabled" population.
// It is observed on assembly="enabled" even though nothing was injected and the
// directive-only path served the response.
func TestUnit_ForwardChat_FailOpenSamplesEnabledPopulation(t *testing.T) {
	t.Parallel()
	reg := metrics.NewProxy("proxy-overhead-fail-open-test")
	h := embedMetadataHandler(&fakeContextAssembler{result: contextclient.AssembleResult{
		Fallback: true, FallbackReason: "DeadlineExceeded",
	}})
	h.metrics = reg
	rec := forwardTimed(t, h, false)

	if got := rec.Header().Get(headerContextFallback); got != "true" {
		t.Fatalf("%s=%q want true", headerContextFallback, got)
	}
	assertHistogramCount(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyEnabled), 1)
	assertHistogramCount(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyDisabled), 0)
	assertAssemblyCounter(t, reg, assemblySeries("ibex_proxy_nonstreaming_requests_total", metrics.ProxyAssemblyEnabled), 1)
}

// TestUnit_ObserveProxyOverheadAt_BucketBoundary is the regression test for the
// truncation defect: the sample is taken from full-precision durations, so a
// 20.4 ms overhead lands above the le="0.02" bucket instead of truncating to
// 20 ms and passing the ratified objective. The clock is injected, so the sample
// is exactly the overhead named in the case.
func TestUnit_ObserveProxyOverheadAt_BucketBoundary(t *testing.T) {
	t.Parallel()
	const providerMs = 80
	start := time.Date(2026, time.November, 12, 9, 0, 0, 0, time.UTC)
	tests := []struct {
		name          string
		overhead      time.Duration
		wantIn20ms    bool
		wantSampleSum float64
	}{
		{
			// 20.4 ms: truncating to milliseconds first would give 20 ms and pass.
			name:          "just_over_20ms_breaches",
			overhead:      20*time.Millisecond + 400*time.Microsecond,
			wantSampleSum: 0.0204,
		},
		{
			name:          "just_under_20ms_passes",
			overhead:      20*time.Millisecond - 400*time.Microsecond,
			wantIn20ms:    true,
			wantSampleSum: 0.0196,
		},
		{
			// The classic truncation case: 20.9 ms must not read as 20 ms.
			name:          "truncation_cannot_hide_a_breach",
			overhead:      20*time.Millisecond + 900*time.Microsecond,
			wantSampleSum: 0.0209,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			reg := metrics.NewProxy("overhead-boundary-" + tc.name)
			ctx := WithRequestStart(context.Background(), start)
			ctx = withProviderDurationMs(ctx, providerMs)
			ctx = withContextAssembleMeta(ctx, contextAssembleMeta{overhead: reg})
			observeProxyOverheadAt(ctx, start.Add(time.Duration(providerMs)*time.Millisecond+tc.overhead))

			hist := histogramSeries(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyDisabled))
			if got := hist.GetSampleCount(); got != 1 {
				t.Fatalf("samples=%d want 1", got)
			}
			got20 := bucketCount(t, hist, 0.020)
			gotSum := hist.GetSampleSum()
			t.Logf("overhead=%v le=0.02 count=%d sample_sum=%v want_in_bucket=%t",
				tc.overhead, got20, gotSum, tc.wantIn20ms)
			want20 := uint64(0)
			if tc.wantIn20ms {
				want20 = 1
			}
			if got20 != want20 {
				t.Fatalf("le=0.02 cumulative count=%d want %d for %v overhead", got20, want20, tc.overhead)
			}
			if math.Abs(gotSum-tc.wantSampleSum) > 1e-12 {
				t.Fatalf("sample sum=%v want %v (full-precision overhead, not a millisecond truncation)",
					gotSum, tc.wantSampleSum)
			}
		})
	}
}

// TestUnit_AttachIbexMetadata_DoesNotObserveOverhead pins the observation point:
// the metadata write happens before the pipeline runs, so it must not record the
// sample — otherwise serialization cost never reaches the histogram.
func TestUnit_AttachIbexMetadata_DoesNotObserveOverhead(t *testing.T) {
	t.Parallel()
	reg := metrics.NewProxy("attach-does-not-observe")
	ctx := WithRequestStart(context.Background(), time.Now().Add(-100*time.Millisecond))
	ctx = withContextAssembleMeta(ctx, contextAssembleMeta{Attempted: true, overhead: reg})

	attached := attachIbexMetadataForPipeline(ctx)
	if _, ok := responsepipeline.IbexMetadataFromContext(attached); !ok {
		t.Fatal("expected ibex metadata for an attempted assembly")
	}
	assertHistogramCount(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyDisabled), 0)
	assertHistogramCount(t, reg, assemblySeries("ibex_proxy_overhead_seconds", metrics.ProxyAssemblyEnabled), 0)
	assertAssemblyCounter(t, reg, assemblySeries("ibex_proxy_nonstreaming_requests_total", metrics.ProxyAssemblyDisabled), 0)
}

// TestUnit_FinishProxyOverheadObservation_Noops covers the three ways the
// observation point fires with nothing to record: no assemble metadata in the
// context, metadata with no recorder wired, and metadata with no request start.
func TestUnit_FinishProxyOverheadObservation_Noops(t *testing.T) {
	t.Parallel()
	obs := &recordingOverheadRecorder{}
	finishProxyOverheadObservation(context.Background())
	finishProxyOverheadObservation(withContextAssembleMeta(context.Background(), contextAssembleMeta{overhead: obs}))
	finishProxyOverheadObservation(withContextAssembleMeta(context.Background(), contextAssembleMeta{Attempted: true}))
	if obs.calls != 0 {
		t.Fatalf("recorded %d observations, want none", obs.calls)
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

			hist := histogramFamily(t, reg, "ibex_proxy_context_assemble_seconds")
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

// TestUnit_ApplyContextOrDirective_AttemptedIsPopulationLabel pins the label
// derivation at its source: the `assembly` population is Attempted — did the
// Assemble RPC run — not whether context was finally injected. A fail-open or
// empty result still spent RPC wall time inside the request, so it reports as
// assembly-enabled; only the skip paths (flag off, nil client, Skip-Memory) are
// the ratified directive-only population.
func TestUnit_ApplyContextOrDirective_AttemptedIsPopulationLabel(t *testing.T) {
	t.Parallel()
	assembler := func(result contextclient.AssembleResult) contextAssembler {
		return &fakeContextAssembler{result: result}
	}
	tests := []struct {
		name    string
		enabled bool
		client  contextAssembler
		want    bool
	}{
		{name: "flag_off_is_disabled", enabled: false, client: assembler(contextclient.AssembleResult{AssembledContext: "x"})},
		{name: "nil_client_is_disabled", enabled: true, client: nil},
		{name: "injected_is_enabled", enabled: true, client: assembler(contextclient.AssembleResult{AssembledContext: "assembled"}), want: true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			h := contextHandler(tc.enabled, tc.client)
			out := runApplyInjection(t, h, []provider.Message{{Role: "user", Content: "hi"}})
			if out.Meta.Attempted != tc.want {
				t.Fatalf("Attempted=%t want %t (fallback=%t)", out.Meta.Attempted, tc.want, out.Meta.Fallback)
			}
		})
	}
	// Fail-open and empty results still ran the RPC, so they stay enabled.
	for _, tc := range []struct {
		name   string
		result contextclient.AssembleResult
	}{
		{name: "grpc_fallback", result: contextclient.AssembleResult{Fallback: true}},
		{name: "empty_context", result: contextclient.AssembleResult{AssembledContext: "  "}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			h := contextHandler(true, &fakeContextAssembler{result: tc.result})
			out := runApplyInjection(t, h, []provider.Message{{Role: "user", Content: "hi"}})
			if !out.Meta.Attempted {
				t.Fatalf("Attempted=false for a fail-open result (fallback=%t)", out.Meta.Fallback)
			}
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

// recordingOverheadRecorder is the no-op-path witness for the observation point.
type recordingOverheadRecorder struct {
	calls        int
	lastAssembly bool
	lastSeconds  float64
}

func (r *recordingOverheadRecorder) ObserveNonStreamingProxyOverhead(assemblyEnabled bool, seconds float64) {
	r.calls++
	r.lastAssembly = assemblyEnabled
	r.lastSeconds = seconds
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

// assemblyLabel is the label key whose value selects the SLO population: did
// the context-assembly RPC run for this request.
const assemblyLabel = "assembly"

// metricQuery names one `assembly`-labelled series to dig out of the gathered
// families: the family called name, carrying assembly=assembly.
type metricQuery struct {
	name     string
	assembly string
}

// assemblySeries is the query for the series carrying assembly=value in the
// family called name.
func assemblySeries(name, value string) metricQuery {
	return metricQuery{name: name, assembly: value}
}

// histogramSeries returns the `assembly` series of a labelled histogram family.
func histogramSeries(t *testing.T, reg *metrics.ProxyRegistry, q metricQuery) *dto.Histogram {
	t.Helper()
	return metricWithLabel(t, reg, q).GetHistogram()
}

// histogramFamily returns the only (unlabelled) metric of a histogram family.
func histogramFamily(t *testing.T, reg *metrics.ProxyRegistry, name string) *dto.Histogram {
	t.Helper()
	mf := findFamily(gatherFamilies(t, reg), name)
	if mf == nil {
		t.Fatalf("missing %s family", name)
	}
	if len(mf.GetMetric()) != 1 {
		t.Fatalf("%s series=%d want 1 unlabelled series", name, len(mf.GetMetric()))
	}
	return mf.GetMetric()[0].GetHistogram()
}

func metricWithLabel(t *testing.T, reg *metrics.ProxyRegistry, q metricQuery) *dto.Metric {
	t.Helper()
	m := findMetric(findFamily(gatherFamilies(t, reg), q.name), q)
	if m == nil {
		t.Fatalf("%s has no assembly=%q series", q.name, q.assembly)
	}
	return m
}

// findFamily returns the gathered family called name, or nil when it is absent.
func findFamily(families []*dto.MetricFamily, name string) *dto.MetricFamily {
	for _, mf := range families {
		if mf.GetName() == name {
			return mf
		}
	}
	return nil
}

// findMetric returns the series of mf that q selects, or nil when mf is absent
// or carries no such series.
func findMetric(mf *dto.MetricFamily, q metricQuery) *dto.Metric {
	if mf == nil {
		return nil
	}
	for _, m := range mf.GetMetric() {
		if carriesLabel(m, assemblyLabel, q.assembly) {
			return m
		}
	}
	return nil
}

// carriesLabel reports whether m carries the label pair key=value.
func carriesLabel(m *dto.Metric, key, value string) bool {
	for _, lp := range m.GetLabel() {
		if lp.GetName() == key && lp.GetValue() == value {
			return true
		}
	}
	return false
}

func gatherFamilies(t *testing.T, reg *metrics.ProxyRegistry) []*dto.MetricFamily {
	t.Helper()
	mfs, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	return mfs
}

func assertHistogramCount(t *testing.T, reg *metrics.ProxyRegistry, q metricQuery, want uint64) {
	t.Helper()
	if got := histogramSeries(t, reg, q).GetSampleCount(); got != want {
		t.Fatalf("%s{assembly=%q} samples=%d want %d", q.name, q.assembly, got, want)
	}
}

func assertAssemblyCounter(t *testing.T, reg *metrics.ProxyRegistry, q metricQuery, want float64) {
	t.Helper()
	got := metricWithLabel(t, reg, q).GetCounter().GetValue()
	if math.Abs(got-want) > 1e-12 {
		t.Fatalf("%s{assembly=%q}=%v want %v", q.name, q.assembly, got, want)
	}
}

// bucketCount returns the cumulative count of the bucket whose upper bound is
// bound, i.e. the value the SLO ratio rules divide by.
func bucketCount(t *testing.T, h *dto.Histogram, bound float64) uint64 {
	t.Helper()
	for _, b := range h.GetBucket() {
		if math.Abs(b.GetUpperBound()-bound) < 1e-12 {
			return b.GetCumulativeCount()
		}
	}
	t.Fatalf("missing le=%v bucket", bound)
	return 0
}

// BenchmarkFinishProxyOverheadObservation is the allocation evidence for the
// new response-path observation point: both assembly series are pre-registered in
// the registry, so the per-request work is two context lookups, one subtraction,
// one atomic histogram add and one counter add.
func BenchmarkFinishProxyOverheadObservation(b *testing.B) {
	reg := metrics.NewProxy("bench-finish-observation")
	for _, tc := range []struct {
		name      string
		assembled bool
	}{
		{name: "assembly_disabled"},
		{name: "assembly_enabled", assembled: true},
	} {
		b.Run(tc.name, func(b *testing.B) {
			ctx := WithRequestStart(context.Background(), time.Now().Add(-100*time.Millisecond))
			ctx = withProviderDurationMs(ctx, 90)
			ctx = withContextAssembleMeta(ctx, contextAssembleMeta{
				Attempted: tc.assembled, overhead: reg,
			})
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				finishProxyOverheadObservation(ctx)
			}
		})
	}
}
