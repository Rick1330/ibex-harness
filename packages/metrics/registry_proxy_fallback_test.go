package metrics

import "testing"

func TestProxyRegistry_ProviderFallbackMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("fallback-metrics-test")
	reg.IncProviderFallback("provider_5xx")
	reg.IncProviderFallback("provider_circuit_open")
	reg.IncProviderFallback("")

	families := gatherFamilies(t, reg.Gatherer())
	fam := families["ibex_proxy_fallbacks_total"]
	if fam == nil {
		t.Fatal("missing ibex_proxy_fallbacks_total")
	}
	if got := counterByLabel(fam, "reason", "provider_5xx"); got != 1 {
		t.Fatalf("5xx=%v", got)
	}
	if got := counterByLabel(fam, "reason", "provider_circuit_open"); got != 1 {
		t.Fatalf("circuit=%v", got)
	}
	if got := counterByLabel(fam, "reason", "unknown"); got != 1 {
		t.Fatalf("empty reason=%v", got)
	}
	if got := counterByLabel(fam, "reason", "provider_timeout"); got != 0 {
		t.Fatalf("timeout materialized=%v", got)
	}
}

func TestProxyRegistry_ProviderFallbackMetrics_NilSafe(t *testing.T) {
	t.Parallel()
	var nilReg *ProxyRegistry
	nilReg.IncProviderFallback("provider_5xx")
	(&ProxyRegistry{}).IncProviderFallback("provider_5xx")
}
