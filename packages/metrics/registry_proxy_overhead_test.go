package metrics

import (
	"math"
	"testing"

	dto "github.com/prometheus/client_model/go"
)

// TestUnit_ProxyRegistry_EnforcementHistograms pins the two SLO series this
// package now exposes: the ratified proxy-overhead SLO (p99 <= 20 ms) and the
// context-assembly RPC duration. It asserts the bucket bounds literally, because
// the 20 ms boundary is what makes the SLO readable from the scrape.
func TestUnit_ProxyRegistry_EnforcementHistograms(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy-overhead")
	reg.ObserveProxyOverheadSeconds(0.012)
	reg.ObserveProxyOverheadSeconds(0.018)
	reg.ObserveContextAssembleSeconds(0.008)

	families := gatherFamilies(t, reg.Gatherer())
	overhead := histograms(families, "ibex_proxy_overhead_seconds")
	if len(overhead) != 1 {
		t.Fatalf("ibex_proxy_overhead_seconds samples=%d want 1", len(overhead))
	}
	assertEnforcementBuckets(t, overhead[0].GetHistogram())
	assertSampleCount(t, overhead[0].GetHistogram(), 2)
	assertSampleSum(t, overhead[0].GetHistogram(), 0.030)

	assemble := histograms(families, "ibex_proxy_context_assemble_seconds")
	if len(assemble) != 1 {
		t.Fatalf("ibex_proxy_context_assemble_seconds samples=%d want 1", len(assemble))
	}
	assertEnforcementBuckets(t, assemble[0].GetHistogram())
	assertSampleCount(t, assemble[0].GetHistogram(), 1)
	assertSampleSum(t, assemble[0].GetHistogram(), 0.008)
}

// TestUnit_ObserveOverhead_RejectsInvalidSamples proves the guards: a nil
// registry, a zero-value registry and a nonsensical duration never reach Observe.
func TestUnit_ObserveOverhead_RejectsInvalidSamples(t *testing.T) {
	t.Parallel()
	var nilReg *ProxyRegistry
	nilReg.ObserveProxyOverheadSeconds(0.001)
	nilReg.ObserveContextAssembleSeconds(0.001)

	empty := &ProxyRegistry{}
	empty.ObserveProxyOverheadSeconds(0.001)
	empty.ObserveContextAssembleSeconds(0.001)

	reg := NewProxy("test-proxy-overhead-invalid")
	reg.ObserveProxyOverheadSeconds(-0.001)
	reg.ObserveProxyOverheadSeconds(math.NaN())
	reg.ObserveProxyOverheadSeconds(math.Inf(1))
	reg.ObserveContextAssembleSeconds(-1)

	h := histograms(gatherFamilies(t, reg.Gatherer()), "ibex_proxy_overhead_seconds")
	if len(h) != 1 || h[0].GetHistogram().GetSampleCount() != 0 {
		t.Fatalf("invalid overhead samples were recorded")
	}
	a := histograms(gatherFamilies(t, reg.Gatherer()), "ibex_proxy_context_assemble_seconds")
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

// BenchmarkObserveProxyOverheadSeconds is the allocation evidence for the
// response-path change: the histogram is pre-registered and unlabelled, so an
// observation is one atomic add with no allocation.
func BenchmarkObserveProxyOverheadSeconds(b *testing.B) {
	reg := NewProxy("bench-proxy-overhead")
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		reg.ObserveProxyOverheadSeconds(0.012)
	}
}
