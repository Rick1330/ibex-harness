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
	r.budgetReservations = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_budget_reservations_total",
		Help: "Durable budget reservation outcomes on the proxy admission path.",
	}, []string{"outcome"})
	r.budgetReservationSec = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_proxy_budget_reservation_duration_seconds",
		Help:    "Wall time of durable budget reservation claims and settlements.",
		Buckets: LatencyBuckets,
	})
	for _, outcome := range []string{
		BudgetReservationClaimed, BudgetReservationNoCap, BudgetReservationExceeded,
		BudgetReservationInProgress, BudgetReservationConflict, BudgetReservationUnavailable,
		BudgetReservationFinalizedComplete, BudgetReservationFinalizedEstimated,
		BudgetReservationFinalizeFailed, BudgetReservationReleased, BudgetReservationReleaseFailed,
	} {
		r.budgetReservations.WithLabelValues(outcome)
	}
}

// Budget reservation outcome labels (bounded; never org/key labeled).
const (
	BudgetReservationClaimed            = "claimed"
	BudgetReservationNoCap              = "no_cap"
	BudgetReservationExceeded           = "exceeded"
	BudgetReservationInProgress         = "in_progress"
	BudgetReservationConflict           = "conflict"
	BudgetReservationUnavailable        = "unavailable"
	BudgetReservationFinalizedComplete  = "finalized_complete"
	BudgetReservationFinalizedEstimated = "finalized_estimated"
	BudgetReservationFinalizeFailed     = "finalize_failed"
	BudgetReservationReleased           = "released"
	BudgetReservationReleaseFailed      = "release_failed"
)

// IncBudgetReservation records a durable budget reservation outcome.
func (r *ProxyRegistry) IncBudgetReservation(outcome string) {
	if r == nil || r.budgetReservations == nil {
		return
	}
	r.budgetReservations.WithLabelValues(boundBudgetReservationOutcome(outcome)).Inc()
}

// ObserveBudgetReservationDurationSeconds records claim/settle wall time.
func (r *ProxyRegistry) ObserveBudgetReservationDurationSeconds(seconds float64) {
	if r == nil || r.budgetReservationSec == nil {
		return
	}
	r.budgetReservationSec.Observe(seconds)
}

func boundBudgetReservationOutcome(outcome string) string {
	switch outcome {
	case BudgetReservationClaimed, BudgetReservationNoCap, BudgetReservationExceeded,
		BudgetReservationInProgress, BudgetReservationConflict, BudgetReservationUnavailable,
		BudgetReservationFinalizedComplete, BudgetReservationFinalizedEstimated,
		BudgetReservationFinalizeFailed, BudgetReservationReleased, BudgetReservationReleaseFailed:
		return outcome
	default:
		return BudgetReservationUnavailable
	}
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
