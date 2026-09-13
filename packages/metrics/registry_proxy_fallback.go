package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initProviderFallbackMetrics() {
	r.providerFallbacksTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_fallbacks_total",
		Help: "Successful provider fallback substitutions by eligibility reason (ADR-0077).",
	}, []string{"reason"})
	// Materialize known reason series so scrape targets stay stable.
	for _, reason := range []string{
		"provider_circuit_open",
		"provider_5xx",
		"provider_timeout",
	} {
		r.providerFallbacksTotal.WithLabelValues(reason)
	}
}

// IncProviderFallback records one successful primary→fallback substitution.
// reason must be a stable label (provider_circuit_open|provider_5xx|provider_timeout).
func (r *ProxyRegistry) IncProviderFallback(reason string) {
	if r == nil || r.providerFallbacksTotal == nil {
		return
	}
	if reason == "" {
		reason = "unknown"
	}
	r.providerFallbacksTotal.WithLabelValues(reason).Inc()
}
