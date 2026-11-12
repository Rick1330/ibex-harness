package metrics

import (
	"math"
	"strings"
	"testing"

	dto "github.com/prometheus/client_model/go"
)

// TestUnit_ProxyRegistry_EnforcementHistograms pins the two SLO series this
// package exposes and the `assembly` population label that partitions the
// overhead one: both label values are registered at construction, so a scrape
// shows both populations from process start, and one call records the sample and
// the traffic counter on the same series.
func TestUnit_ProxyRegistry_EnforcementHistograms(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy-overhead")

	// Pre-registration: both populations are scrapeable before any request ends.
	families := gatherFamilies(t, reg.Gatherer())
	for _, assembly := range []string{ProxyAssemblyDisabled, ProxyAssemblyEnabled} {
		h := metricWithAssembly(t, families, "ibex_proxy_overhead_seconds", assembly)
		assertEnforcementBuckets(t, h.GetHistogram())
		assertSampleCount(t, h.GetHistogram(), 0)
		assertCounterValue(t, families, "ibex_proxy_nonstreaming_requests_total", assembly, 0)
	}

	reg.ObserveNonStreamingProxyOverhead(false, 0.012)
	reg.ObserveNonStreamingProxyOverhead(false, 0.018)
	reg.ObserveNonStreamingProxyOverhead(true, 0.040)
	reg.ObserveContextAssembleSeconds(0.008)

	families = gatherFamilies(t, reg.Gatherer())
	disabled := metricWithAssembly(t, families, "ibex_proxy_overhead_seconds", ProxyAssemblyDisabled)
	assertSampleCount(t, disabled.GetHistogram(), 2)
	assertSampleSum(t, disabled.GetHistogram(), 0.030)
	assertCounterValue(t, families, "ibex_proxy_nonstreaming_requests_total", ProxyAssemblyDisabled, 2)

	enabled := metricWithAssembly(t, families, "ibex_proxy_overhead_seconds", ProxyAssemblyEnabled)
	assertEnforcementBuckets(t, enabled.GetHistogram())
	assertSampleCount(t, enabled.GetHistogram(), 1)
	assertSampleSum(t, enabled.GetHistogram(), 0.040)
	assertCounterValue(t, families, "ibex_proxy_nonstreaming_requests_total", ProxyAssemblyEnabled, 1)

	assemble := histograms(families, "ibex_proxy_context_assemble_seconds")
	if len(assemble) != 1 {
		t.Fatalf("ibex_proxy_context_assemble_seconds samples=%d want 1", len(assemble))
	}
	assertEnforcementBuckets(t, assemble[0].GetHistogram())
	assertSampleCount(t, assemble[0].GetHistogram(), 1)
	assertSampleSum(t, assemble[0].GetHistogram(), 0.008)
}

// TestUnit_ObserveOverhead_RejectsInvalidSamples proves the guards: a nil
// registry, a zero-value registry and a nonsensical duration never reach Observe,
// and a rejected sample never increments the traffic counter either — the two
// series cannot diverge.
func TestUnit_ObserveOverhead_RejectsInvalidSamples(t *testing.T) {
	t.Parallel()
	var nilReg *ProxyRegistry
	nilReg.ObserveNonStreamingProxyOverhead(false, 0.001)
	nilReg.ObserveContextAssembleSeconds(0.001)

	empty := &ProxyRegistry{}
	empty.ObserveNonStreamingProxyOverhead(true, 0.001)
	empty.ObserveContextAssembleSeconds(0.001)

	reg := NewProxy("test-proxy-overhead-invalid")
	reg.ObserveNonStreamingProxyOverhead(false, -0.001)
	reg.ObserveNonStreamingProxyOverhead(true, math.NaN())
	reg.ObserveNonStreamingProxyOverhead(true, math.Inf(1))
	reg.ObserveContextAssembleSeconds(-1)

	families := gatherFamilies(t, reg.Gatherer())
	for _, assembly := range []string{ProxyAssemblyDisabled, ProxyAssemblyEnabled} {
		h := metricWithAssembly(t, families, "ibex_proxy_overhead_seconds", assembly)
		if got := h.GetHistogram().GetSampleCount(); got != 0 {
			t.Fatalf("invalid overhead samples were recorded for assembly=%q", assembly)
		}
		assertCounterValue(t, families, "ibex_proxy_nonstreaming_requests_total", assembly, 0)
	}
	a := histograms(families, "ibex_proxy_context_assemble_seconds")
	if len(a) != 1 || a[0].GetHistogram().GetSampleCount() != 0 {
		t.Fatalf("invalid assemble samples were recorded")
	}
}

// TestUnit_ProxyEnforcementBuckets_ReadableAt20ms locks the family to the bounds
// the SLO arithmetic depends on: 1/2.5/5/10/20 ms individually, terminating at 10 s.
func TestUnit_ProxyEnforcementBuckets_ReadableAt20ms(t *testing.T) {
	t.Parallel()
	want := []float64{
		0.001, 0.0025, 0.005, 0.010, 0.020, 0.050, 0.100,
		0.250, 0.500, 1.000, 2.500, 5.000, 10.000,
	}
	if len(ProxyEnforcementBuckets) != len(want) {
		t.Fatalf("buckets=%v want %v", ProxyEnforcementBuckets, want)
	}
	for i := range want {
		if ProxyEnforcementBuckets[i] != want[i] {
			t.Fatalf("bucket[%d]=%v want %v", i, ProxyEnforcementBuckets[i], want[i])
		}
	}
}

func histograms(families map[string]*dto.MetricFamily, name string) []*dto.Metric {
	mf := families[name]
	if mf == nil {
		return nil
	}
	return mf.GetMetric()
}

// TestUnit_Exposition_OverheadPopulations serves the registry through the real
// Prometheus handler and pins the scrape shape the recording rules read: both
// `assembly` populations on the histogram and on the traffic counter, with the
// 0.02 bucket still present on each population.
func TestUnit_Exposition_OverheadPopulations(t *testing.T) {
	t.Parallel()
	reg := NewProxy("proxy-exposition")
	reg.ObserveNonStreamingProxyOverhead(false, 0.012)
	reg.ObserveNonStreamingProxyOverhead(false, 0.021)
	reg.ObserveNonStreamingProxyOverhead(true, 0.004)

	scrape := scrapeMetrics(t, reg.Gatherer())
	for _, line := range strings.Split(scrape, "\n") {
		if strings.Contains(line, "ibex_proxy_overhead_seconds") ||
			strings.Contains(line, "ibex_proxy_nonstreaming_requests_total") {
			t.Log(line)
		}
	}
	for _, want := range []string{
		`ibex_proxy_overhead_seconds_count{assembly="disabled"} 2`,
		`ibex_proxy_overhead_seconds_count{assembly="enabled"} 1`,
		`ibex_proxy_overhead_seconds_bucket{assembly="disabled",le="0.02"} 1`,
		`ibex_proxy_overhead_seconds_bucket{assembly="enabled",le="0.02"} 1`,
		`ibex_proxy_nonstreaming_requests_total{assembly="disabled"} 2`,
		`ibex_proxy_nonstreaming_requests_total{assembly="enabled"} 1`,
	} {
		if !strings.Contains(scrape, want) {
			t.Fatalf("scrape is missing %q", want)
		}
	}
}

// metricWithAssembly returns the series of name whose `assembly` label equals
// assembly, failing the test when the series is missing.
func metricWithAssembly(t *testing.T, families map[string]*dto.MetricFamily, name, assembly string) *dto.Metric {
	t.Helper()
	for _, m := range histograms(families, name) {
		for _, lp := range m.GetLabel() {
			if lp.GetName() == proxyAssemblyLabel && lp.GetValue() == assembly {
				return m
			}
		}
	}
	t.Fatalf("%s has no %s=%q series", name, proxyAssemblyLabel, assembly)
	return nil
}

func assertCounterValue(t *testing.T, families map[string]*dto.MetricFamily, name, assembly string, want float64) {
	t.Helper()
	got := metricWithAssembly(t, families, name, assembly).GetCounter().GetValue()
	if math.Abs(got-want) > 1e-12 {
		t.Fatalf("%s{%s=%q}=%v want %v", name, proxyAssemblyLabel, assembly, got, want)
	}
}

func assertEnforcementBuckets(t *testing.T, h *dto.Histogram) {
	t.Helper()
	bounds := h.GetBucket()
	if len(bounds) != len(ProxyEnforcementBuckets) {
		t.Fatalf("scraped buckets=%d want %d", len(bounds), len(ProxyEnforcementBuckets))
	}
	for i, b := range bounds {
		if math.Abs(b.GetUpperBound()-ProxyEnforcementBuckets[i]) > 1e-12 {
			t.Fatalf("bucket[%d] upper bound=%v want %v", i, b.GetUpperBound(), ProxyEnforcementBuckets[i])
		}
	}
}

func assertSampleCount(t *testing.T, h *dto.Histogram, want uint64) {
	t.Helper()
	if got := h.GetSampleCount(); got != want {
		t.Fatalf("sample count=%d want %d", got, want)
	}
}

func assertSampleSum(t *testing.T, h *dto.Histogram, want float64) {
	t.Helper()
	if got := h.GetSampleSum(); math.Abs(got-want) > 1e-9 {
		t.Fatalf("sample sum=%v want %v", got, want)
	}
}

// BenchmarkObserveNonStreamingProxyOverhead is the allocation evidence for the
// labelled response path: both assembly series are resolved at construction, so
// an observation is one atomic histogram add plus one counter add, with no label
// lookup and no allocation.
func BenchmarkObserveNonStreamingProxyOverhead(b *testing.B) {
	reg := NewProxy("bench-proxy-overhead")
	for _, tc := range []struct {
		name    string
		enabled bool
	}{
		{name: ProxyAssemblyDisabled},
		{name: ProxyAssemblyEnabled, enabled: true},
	} {
		b.Run(tc.name, func(b *testing.B) {
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				reg.ObserveNonStreamingProxyOverhead(tc.enabled, 0.012)
			}
		})
	}
}
