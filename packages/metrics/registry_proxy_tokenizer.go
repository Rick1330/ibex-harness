package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initTokenizerMetrics() {
	r.tokenizerCountTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_tokenizer_count_total",
		Help: "Tokenizer Count invocations by family and result.",
	}, []string{"family", "result"})
	r.tokenizerCountSeconds = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_tokenizer_count_duration_seconds",
		Help:    "Tokenizer Count wall time in seconds.",
		Buckets: LatencyBuckets,
	}, []string{"family"})
}

// ObserveTokenizerCount records a tokenizer Count outcome and duration.
func (r *ProxyRegistry) ObserveTokenizerCount(family, result string, seconds float64) {
	if r == nil || r.tokenizerCountTotal == nil {
		return
	}
	r.tokenizerCountTotal.WithLabelValues(family, result).Inc()
	r.tokenizerCountSeconds.WithLabelValues(family).Observe(seconds)
}
