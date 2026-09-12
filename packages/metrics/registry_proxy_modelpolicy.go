package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initModelPolicyMetrics() {
	r.modelPolicyCacheHits = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_model_policy_cache_hits_total",
		Help: "Model-policy cache hits by tier.",
	}, []string{"tier"})
	r.modelPolicyCacheMisses = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_model_policy_cache_misses_total",
		Help: "Model-policy cache misses by tier.",
	}, []string{"tier"})
	r.modelPolicyCacheHits.WithLabelValues("lru")
	r.modelPolicyCacheMisses.WithLabelValues("lru")
	r.modelPolicyDeny = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_model_policy_deny_total",
		Help: "Org model-policy denials on the proxy hot path.",
	})
	r.modelPolicyInvalidate = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_model_policy_invalidate_total",
		Help: "Model-policy cache invalidations (pub/sub or local).",
	})
	r.modelPolicyLRUSize = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ibex_proxy_model_policy_lru_size",
		Help: "Current number of orgs in the model-policy LRU.",
	})
}

// IncCacheHit implements modelpolicy.Metrics.
func (r *ProxyRegistry) IncCacheHit(tier string) {
	if r == nil || r.modelPolicyCacheHits == nil {
		return
	}
	r.modelPolicyCacheHits.WithLabelValues(tier).Inc()
}

// IncCacheMiss implements modelpolicy.Metrics.
func (r *ProxyRegistry) IncCacheMiss(tier string) {
	if r == nil || r.modelPolicyCacheMisses == nil {
		return
	}
	r.modelPolicyCacheMisses.WithLabelValues(tier).Inc()
}

// IncDeny implements modelpolicy.Metrics.
func (r *ProxyRegistry) IncDeny() {
	if r == nil || r.modelPolicyDeny == nil {
		return
	}
	r.modelPolicyDeny.Inc()
}

// IncInvalidate implements modelpolicy.Metrics.
func (r *ProxyRegistry) IncInvalidate() {
	if r == nil || r.modelPolicyInvalidate == nil {
		return
	}
	r.modelPolicyInvalidate.Inc()
}

// SetLRUSize implements modelpolicy.Metrics.
func (r *ProxyRegistry) SetLRUSize(n float64) {
	if r == nil || r.modelPolicyLRUSize == nil {
		return
	}
	r.modelPolicyLRUSize.Set(n)
}
