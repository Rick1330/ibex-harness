package metrics

import (
	"math"

	"github.com/prometheus/client_golang/prometheus"
)

// Enforcement overhead metrics are unlabelled histograms on purpose: they are
// observed once per completed request on the proxy's response path, so a
// HistogramVec would add a label lookup (and a label-values slice escape) to the
// hot path for a label whose value is constant on the only path instrumented.
func (r *ProxyRegistry) initEnforcementOverheadMetrics() {
	r.proxyOverheadSeconds = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name: "ibex_proxy_overhead_seconds",
		Help: "Proxy enforcement overhead per completed non-streaming request: " +
			"wall time since request start minus upstream provider Complete time, " +
			"clamped at zero. Ratified SLO: p99 <= 20 ms.",
		Buckets: ProxyEnforcementBuckets,
	})
	r.contextAssembleSeconds = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name: "ibex_proxy_context_assemble_seconds",
		Help: "Context Assemble RPC wall time observed by the proxy, including " +
			"fail-open outcomes. Target: p95 <= 50 ms.",
		Buckets: ProxyEnforcementBuckets,
	})
}

// ObserveProxyOverheadSeconds records one request's enforcement overhead, i.e.
// exactly the value reported as proxy_overhead_ms in the embedded ibex block.
func (r *ProxyRegistry) ObserveProxyOverheadSeconds(seconds float64) {
	if r == nil {
		return
	}
	observeDuration(r.proxyOverheadSeconds, seconds)
}

// ObserveContextAssembleSeconds records one Context Assemble RPC duration as
// seen by the proxy; fail-open results are included.
func (r *ProxyRegistry) ObserveContextAssembleSeconds(seconds float64) {
	if r == nil {
		return
	}
	observeDuration(r.contextAssembleSeconds, seconds)
}

// sampleIsValid reports whether d is a duration a histogram may record: finite
// and non-negative. A negative, NaN or infinite sample would corrupt the bucket
// arithmetic, so it never reaches Observe.
func sampleIsValid(d float64) bool {
	if d < 0 {
		return false
	}
	if math.IsNaN(d) {
		return false
	}
	return !math.IsInf(d, 0)
}

// observeDuration rejects the values that would corrupt a histogram: a nil
// collector (metrics not wired) and negative or non-finite durations.
func observeDuration(h prometheus.Histogram, seconds float64) {
	if h == nil {
		return
	}
	if !sampleIsValid(seconds) {
		return
	}
	h.Observe(seconds)
}
