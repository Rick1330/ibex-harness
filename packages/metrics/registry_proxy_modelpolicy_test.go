package metrics

import "testing"

func TestProxyRegistry_ModelPolicyMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("model-policy-metrics-test")
	reg.IncCacheHit("lru")
	reg.IncCacheMiss("lru")
	reg.IncDeny()
	reg.IncInvalidate()
	reg.SetLRUSize(3)

	families := gatherFamilies(t, reg.Gatherer())
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
	gauge := families["ibex_proxy_model_policy_lru_size"]
	if gauge == nil || len(gauge.GetMetric()) == 0 {
		t.Fatal("missing lru size gauge")
	}
	if got := gauge.GetMetric()[0].GetGauge().GetValue(); got != 3 {
		t.Fatalf("lru size=%v want 3", got)
	}

	var nilReg *ProxyRegistry
	nilReg.IncCacheHit("lru")
	nilReg.IncCacheMiss("lru")
	nilReg.IncDeny()
	nilReg.IncInvalidate()
	nilReg.SetLRUSize(0)
}
