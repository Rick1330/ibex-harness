package metrics

import (
	"math"

	"github.com/prometheus/client_golang/prometheus"
)

// Values of the `assembly` label carried by ibex_proxy_overhead_seconds and
// ibex_proxy_nonstreaming_requests_total. They partition every completed
// non-streaming request by whether the response actually carried assembled
// context, and the value set is closed:
//
//   - ProxyAssemblyDisabled: the request took the directive-only path — context
//     assembly was off, skipped, failed open, or returned nothing to inject.
//     This is the ratified p99 <= 20 ms SLO population.
//   - ProxyAssemblyEnabled: assembled context was injected into the provider
//     messages, so the request paid the Assemble RPC as well. Different work
//     profile, measured as its own series.
//
// Both values are pre-registered at construction, so a label value can never
// grow cardinality and the response path never builds a label-values slice.
const (
	ProxyAssemblyDisabled = "disabled"
	ProxyAssemblyEnabled  = "enabled"
)

const proxyAssemblyLabel = "assembly"

// enforcementOverheadMetrics are the in-proxy, provider-time-excluded latency
// series that back the proxy overhead and context assembly SLOs, plus the
// traffic counter that keeps a missing proxy-overhead sample distinguishable
// from an idle stack.
//
// The overhead histogram and its counter are labelled by `assembly`; both series
// of both families are created here, once, so an observation is a pre-resolved
// observer/counter call with no label hashing and no allocation.
func (r *ProxyRegistry) initEnforcementOverheadMetrics() {
	r.proxyOverheadSeconds = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name: "ibex_proxy_overhead_seconds",
		Help: "Proxy enforcement overhead per completed non-streaming request: " +
			"wall time since request start minus upstream provider Complete time, " +
			"clamped at zero, sampled after the response pipeline ran and the body " +
			"was serialized. assembly=disabled is the directive-only population the " +
			"ratified p99 <= 20 ms objective is read from; assembly=enabled injected " +
			"assembled context and is measured as a separate work profile.",
		Buckets: ProxyEnforcementBuckets,
	}, []string{proxyAssemblyLabel})
	r.nonstreamingRequestsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_nonstreaming_requests_total",
		Help: "Completed non-streaming requests that produced a proxy-overhead " +
			"sample, by assembly population. Incremented in the same call as the " +
			"ibex_proxy_overhead_seconds observation, so traffic > 0 with zero " +
			"observations is a missing SLI rather than real silence.",
	}, []string{proxyAssemblyLabel})
	r.contextAssembleSeconds = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name: "ibex_proxy_context_assemble_seconds",
		Help: "Context Assemble RPC wall time observed by the proxy, including " +
			"fail-open outcomes. Target: p95 <= 50 ms.",
		Buckets: ProxyEnforcementBuckets,
	})
	r.proxyOverheadDisabled = r.proxyOverheadSeconds.WithLabelValues(ProxyAssemblyDisabled)
	r.proxyOverheadEnabled = r.proxyOverheadSeconds.WithLabelValues(ProxyAssemblyEnabled)
	r.nonstreamingDisabled = r.nonstreamingRequestsTotal.WithLabelValues(ProxyAssemblyDisabled)
	r.nonstreamingEnabled = r.nonstreamingRequestsTotal.WithLabelValues(ProxyAssemblyEnabled)
}

// ObserveNonStreamingProxyOverhead records one completed non-streaming request:
// its enforcement overhead sample and the matching traffic-counter increment, on
// the series selected by assemblyEnabled. Both happen in this one call so the
// histogram and the counter cannot diverge — a request is either counted and
// observed, or neither. A nil receiver, an uninitialized registry or a sample a
// histogram must not record (negative, NaN, infinite) records nothing.
func (r *ProxyRegistry) ObserveNonStreamingProxyOverhead(assemblyEnabled bool, seconds float64) {
	if r == nil || !sampleIsValid(seconds) {
		return
	}
	overhead, requests := r.proxyOverheadDisabled, r.nonstreamingDisabled
	if assemblyEnabled {
		overhead, requests = r.proxyOverheadEnabled, r.nonstreamingEnabled
	}
	if overhead == nil || requests == nil {
		return
	}
	overhead.Observe(seconds)
	requests.Inc()
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
