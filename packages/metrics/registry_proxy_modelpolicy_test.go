package metrics

import (
	"testing"

	dto "github.com/prometheus/client_model/go"
)

func TestProxyRegistry_ModelPolicyMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("model-policy-metrics-test")
	seedModelPolicySamples(reg)

	families := gatherFamilies(t, reg.Gatherer())
	assertModelPolicyCounters(t, families)
	assertModelPolicyGauges(t, families, 3, 1)

	reg.SetModelPolicyEnabled(false)
	families = gatherFamilies(t, reg.Gatherer())
	assertGaugeValue(t, families, "ibex_proxy_model_policy_enabled", 0)
}

func TestProxyRegistry_ModelPolicyMetrics_NilSafe(t *testing.T) {
	t.Parallel()
	var nilReg *ProxyRegistry
	nilReg.IncCacheHit("lru")
	nilReg.IncCacheMiss("lru")
	nilReg.IncDeny()
	nilReg.IncInvalidate()
	nilReg.SetLRUSize(0)
	nilReg.SetModelPolicyEnabled(false)
}

func seedModelPolicySamples(reg *ProxyRegistry) {
	reg.IncCacheHit("lru")
	reg.IncCacheMiss("lru")
	reg.IncDeny()
	reg.IncInvalidate()
	reg.SetLRUSize(3)
	reg.SetModelPolicyEnabled(true)
}

func assertModelPolicyCounters(t *testing.T, families map[string]*dto.MetricFamily) {
	t.Helper()
	if got := counterByLabel(families["ibex_proxy_model_policy_cache_hits_total"], "tier", "lru"); got != 1 {
		t.Fatalf("cache hits=%v want 1", got)
	}
	if got := counterByLabel(families["ibex_proxy_model_policy_cache_misses_total"], "tier", "lru"); got != 1 {
		t.Fatalf("cache misses=%v want 1", got)
	}
	if got := counterValue(families["ibex_proxy_model_policy_deny_total"]); got != 1 {
		t.Fatalf("deny=%v want 1", got)
	}
	if got := counterValue(families["ibex_proxy_model_policy_invalidate_total"]); got != 1 {
		t.Fatalf("invalidate=%v want 1", got)
	}
}

func assertModelPolicyGauges(t *testing.T, families map[string]*dto.MetricFamily, wantLRU, wantEnabled float64) {
	t.Helper()
	assertGaugeValue(t, families, "ibex_proxy_model_policy_lru_size", wantLRU)
	assertGaugeValue(t, families, "ibex_proxy_model_policy_enabled", wantEnabled)
}

func assertGaugeValue(t *testing.T, families map[string]*dto.MetricFamily, name string, want float64) {
	t.Helper()
	gauge := families[name]
	if gauge == nil || len(gauge.GetMetric()) == 0 {
		t.Fatalf("missing %s gauge", name)
	}
	if got := gauge.GetMetric()[0].GetGauge().GetValue(); got != want {
		t.Fatalf("%s=%v want %v", name, got, want)
	}
}
