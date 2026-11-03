package metrics

import (
	"testing"

	dto "github.com/prometheus/client_model/go"
)

func TestProxyRegistry_BudgetMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("budget-metrics-test")
	seedBudgetSamples(reg)

	families := gatherFamilies(t, reg.Gatherer())
	assertBudgetCounters(t, families)
	assertBudgetGauges(t, families, 3)

	reg.SetBudgetLRUSize(7)
	families = gatherFamilies(t, reg.Gatherer())
	assertGaugeValue(t, families, "ibex_proxy_budget_lru_size", 7)
}

func TestProxyRegistry_BudgetMetrics_NilSafe(t *testing.T) {
	t.Parallel()
	var nilReg *ProxyRegistry
	nilReg.IncBudgetCacheHit("lru")
	nilReg.IncBudgetCacheMiss("lru")
	nilReg.IncBudgetDeny()
	nilReg.IncBudgetInvalidate()
	nilReg.SetBudgetLRUSize(0)
	nilReg.IncBudgetReservation(BudgetReservationClaimed)
	nilReg.ObserveBudgetReservationDurationSeconds(0.1)
}

func TestProxyRegistry_BudgetReservationMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("budget-reservation-metrics-test")
	reg.IncBudgetReservation(BudgetReservationClaimed)
	reg.IncBudgetReservation(BudgetReservationExceeded)
	reg.IncBudgetReservation("not-a-real-outcome")
	reg.ObserveBudgetReservationDurationSeconds(0.25)

	families := gatherFamilies(t, reg.Gatherer())
	counters := families["ibex_proxy_budget_reservations_total"]
	if got := counterByLabel(counters, "outcome", BudgetReservationClaimed); got != 1 {
		t.Fatalf("claimed=%v want 1", got)
	}
	if got := counterByLabel(counters, "outcome", BudgetReservationExceeded); got != 1 {
		t.Fatalf("exceeded=%v want 1", got)
	}
	if got := counterByLabel(counters, "outcome", BudgetReservationUnavailable); got != 1 {
		t.Fatalf("unknown outcome should clamp to unavailable: %v want 1", got)
	}
	hist := families["ibex_proxy_budget_reservation_duration_seconds"]
	if hist == nil || len(hist.GetMetric()) != 1 || hist.GetMetric()[0].GetHistogram().GetSampleCount() != 1 {
		t.Fatalf("duration histogram missing observation: %+v", hist)
	}
}

func seedBudgetSamples(reg *ProxyRegistry) {
	reg.IncBudgetCacheHit("lru")
	reg.IncBudgetCacheMiss("lru")
	reg.IncBudgetDeny()
	reg.IncBudgetInvalidate()
	reg.SetBudgetLRUSize(3)
}

func assertBudgetCounters(t *testing.T, families map[string]*dto.MetricFamily) {
	t.Helper()
	if got := counterByLabel(families["ibex_proxy_budget_cache_hits_total"], "tier", "lru"); got != 1 {
		t.Fatalf("cache hits=%v want 1", got)
	}
	if got := counterByLabel(families["ibex_proxy_budget_cache_misses_total"], "tier", "lru"); got != 1 {
		t.Fatalf("cache misses=%v want 1", got)
	}
	if got := counterValue(families["ibex_proxy_budget_deny_total"]); got != 1 {
		t.Fatalf("deny=%v want 1", got)
	}
	if got := counterValue(families["ibex_proxy_budget_invalidate_total"]); got != 1 {
		t.Fatalf("invalidate=%v want 1", got)
	}
}

func assertBudgetGauges(t *testing.T, families map[string]*dto.MetricFamily, wantLRU float64) {
	t.Helper()
	assertGaugeValue(t, families, "ibex_proxy_budget_lru_size", wantLRU)
}
