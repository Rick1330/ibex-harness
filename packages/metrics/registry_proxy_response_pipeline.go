package metrics

import (
	"math"

	"github.com/prometheus/client_golang/prometheus"
)

func (r *ProxyRegistry) initResponsePipelineMetrics() {
	r.responsePipelineStageDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_proxy_response_pipeline_stage_duration_seconds",
		Help:    "Non-streaming response pipeline stage wall time in seconds.",
		Buckets: LatencyBuckets,
	}, []string{"stage", "result"})
	r.responsePipelineFailOpenTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_response_pipeline_stage_fail_open_total",
		Help: "Non-critical response pipeline stage failures that fail open.",
	}, []string{"stage"})
}

// ObserveResponsePipelineStageDuration records stage execution outcome and duration.
func (r *ProxyRegistry) ObserveResponsePipelineStageDuration(stage, result string, seconds float64) {
	if r == nil || r.responsePipelineStageDuration == nil {
		return
	}
	if seconds < 0 {
		return
	}
	if math.IsNaN(seconds) {
		return
	}
	if math.IsInf(seconds, 0) {
		return
	}
	r.responsePipelineStageDuration.WithLabelValues(stage, result).Observe(seconds)
}

// IncResponsePipelineStageFailOpen records a fail-open stage error.
func (r *ProxyRegistry) IncResponsePipelineStageFailOpen(stage string) {
	if r == nil || r.responsePipelineFailOpenTotal == nil {
		return
	}
	r.responsePipelineFailOpenTotal.WithLabelValues(stage).Inc()
}
