package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initBillingMetrics() {
	r.budgetCacheHits = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_budget_cache_hits_total",
		Help: "Budget cache hits by tier.",
	}, []string{"tier"})
	r.budgetCacheMisses = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_budget_cache_misses_total",
		Help: "Budget cache misses by tier.",
	}, []string{"tier"})
	r.budgetCacheHits.WithLabelValues("lru")
	r.budgetCacheMisses.WithLabelValues("lru")
	r.budgetDeny = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_budget_deny_total",
		Help: "Org budget hard-cap denials on the proxy hot path.",
	})
	r.budgetInvalidate = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_budget_invalidate_total",
		Help: "Budget cache invalidations (pub/sub or local).",
	})
	r.budgetLRUSize = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ibex_proxy_budget_lru_size",
		Help: "Current number of orgs in the budget LRU.",
	})
}

// IncBudgetCacheHit records a budget cache hit.
func (r *ProxyRegistry) IncBudgetCacheHit(tier string) {
	if r == nil || r.budgetCacheHits == nil {
		return
	}
	r.budgetCacheHits.WithLabelValues(tier).Inc()
}

// IncBudgetCacheMiss records a budget cache miss.
func (r *ProxyRegistry) IncBudgetCacheMiss(tier string) {
	if r == nil || r.budgetCacheMisses == nil {
		return
	}
	r.budgetCacheMisses.WithLabelValues(tier).Inc()
}

// IncBudgetDeny records a hard-cap denial.
func (r *ProxyRegistry) IncBudgetDeny() {
	if r == nil || r.budgetDeny == nil {
		return
	}
	r.budgetDeny.Inc()
}

// IncBudgetInvalidate records a budget cache invalidation.
func (r *ProxyRegistry) IncBudgetInvalidate() {
	if r == nil || r.budgetInvalidate == nil {
		return
	}
	r.budgetInvalidate.Inc()
}

// SetBudgetLRUSize records current budget LRU size.
func (r *ProxyRegistry) SetBudgetLRUSize(n float64) {
	if r == nil || r.budgetLRUSize == nil {
		return
	}
	r.budgetLRUSize.Set(n)
}
