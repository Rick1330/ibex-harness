package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initDirectiveMetrics() {
	r.directiveCacheHits = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_directive_cache_hits_total",
		Help: "Directive Redis cache hits.",
	})
	r.directiveCacheMisses = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_directive_cache_misses_total",
		Help: "Directive Redis cache misses (including Redis errors treated as miss).",
	})
	r.directiveResolveErrs = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_directive_resolve_errors_total",
		Help: "Directive resolve failures from durable store (Postgres).",
	})
	r.directiveResolveSec = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_proxy_directive_resolve_duration_seconds",
		Help:    "Directive Resolve latency including cache and Postgres fallback.",
		Buckets: LatencyBuckets,
	})
	r.directiveInvalidate = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_directive_invalidate_total",
		Help: "Directive cache invalidations applied from Redis pub/sub.",
	})
}

// IncDirectiveCacheHit records a directive Redis cache hit.
func (r *ProxyRegistry) IncDirectiveCacheHit() {
	r.directiveCacheHits.Inc()
}

// IncDirectiveCacheMiss records a directive Redis cache miss.
func (r *ProxyRegistry) IncDirectiveCacheMiss() {
	r.directiveCacheMisses.Inc()
}

// IncDirectiveResolveError records a Postgres/store failure during resolve.
func (r *ProxyRegistry) IncDirectiveResolveError() {
	r.directiveResolveErrs.Inc()
}

// ObserveDirectiveResolveSeconds records Resolve wall time.
func (r *ProxyRegistry) ObserveDirectiveResolveSeconds(seconds float64) {
	r.directiveResolveSec.Observe(seconds)
}

// IncDirectiveInvalidate records a pub/sub-driven cache invalidation.
func (r *ProxyRegistry) IncDirectiveInvalidate() {
	r.directiveInvalidate.Inc()
}
