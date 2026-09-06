package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initContextAssembleMetrics() {
	r.contextAssembleFallbackTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_context_assemble_fallback_total",
		Help: "Context AssembleContext fail-open outcomes by reason (gRPC code, nil_response, or empty).",
	}, []string{"reason"})
}

// Compile-time check: ProxyRegistry satisfies contextclient.AssembleFallbackRecorder via RecordAssembleFallback.
var _ interface {
	RecordAssembleFallback(reason string)
} = (*ProxyRegistry)(nil)

// RecordAssembleFallback implements contextclient.AssembleFallbackRecorder.
func (r *ProxyRegistry) RecordAssembleFallback(reason string) {
	r.IncContextAssembleFallback(reason)
}

// IncContextAssembleFallback records a fail-open Assemble result.
// reason is a stable label (gRPC status code name, nil_response, or empty); never org/agent/query content.
func (r *ProxyRegistry) IncContextAssembleFallback(reason string) {
	if r == nil || r.contextAssembleFallbackTotal == nil {
		return
	}
	if reason == "" {
		reason = "unknown"
	}
	r.contextAssembleFallbackTotal.WithLabelValues(reason).Inc()
}
