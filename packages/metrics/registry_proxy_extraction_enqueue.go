package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initExtractionEnqueueMetrics() {
	r.extractionEnqueueTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_extraction_enqueue_total",
		Help: "Extraction enqueue attempts from session terminate (result=success|failed|skipped).",
	}, []string{"result", "reason"})
}

// IncExtractionEnqueue records enqueue outcome (success|failed|skipped) with a low-cardinality reason.
func (r *ProxyRegistry) IncExtractionEnqueue(result, reason string) {
	if r == nil || r.extractionEnqueueTotal == nil {
		return
	}
	r.extractionEnqueueTotal.WithLabelValues(result, reason).Inc()
}
