package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initAuthCacheMetrics() {
	r.authCacheHits = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_auth_cache_hits_total",
		Help: "Auth cache hits by tier.",
	}, []string{"tier"})
	r.authCacheMisses = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_auth_cache_misses_total",
		Help: "Auth cache misses by tier.",
	}, []string{"tier"})
	// Materialize known low-cardinality series so they appear before any events.
	r.authCacheHits.WithLabelValues("lru")
	r.authCacheMisses.WithLabelValues("lru")
	r.authCacheMisses.WithLabelValues("bloom")
	r.authCacheLRUSize = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ibex_proxy_auth_cache_lru_size",
		Help: "Current number of entries in the auth claims LRU.",
	})
	r.authCacheLRUEvict = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_auth_cache_lru_evictions_total",
		Help: "Auth claims LRU evictions.",
	})
	r.authCacheBloomFP = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_auth_cache_bloom_fp_total",
		Help: "Invalid-token bloom false positives (bloom said invalid, upstream said valid).",
	})
}

// IncAuthCacheHit records an auth cache hit for the given tier.
func (r *ProxyRegistry) IncAuthCacheHit(tier string) {
	r.authCacheHits.WithLabelValues(tier).Inc()
}

// IncAuthCacheMiss records an auth cache miss for the given tier.
func (r *ProxyRegistry) IncAuthCacheMiss(tier string) {
	r.authCacheMisses.WithLabelValues(tier).Inc()
}

// SetAuthCacheLRUSize records the current auth claims LRU size.
func (r *ProxyRegistry) SetAuthCacheLRUSize(n float64) {
	r.authCacheLRUSize.Set(n)
}

// IncAuthCacheLRUEviction records an auth claims LRU eviction.
func (r *ProxyRegistry) IncAuthCacheLRUEviction() {
	r.authCacheLRUEvict.Inc()
}

// IncAuthCacheBloomFP records an invalid-token bloom false positive.
func (r *ProxyRegistry) IncAuthCacheBloomFP() {
	r.authCacheBloomFP.Inc()
}

func (r *ProxyRegistry) initRevocationMetrics() {
	r.revocationInvalidate = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_revocation_invalidate_total",
		Help: "Auth cache invalidations applied from Redis revocation pub/sub.",
	})
}

// IncRevocationInvalidate records a revocation pub/sub invalidate delivery.
func (r *ProxyRegistry) IncRevocationInvalidate() {
	r.revocationInvalidate.Inc()
}
