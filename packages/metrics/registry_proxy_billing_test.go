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
