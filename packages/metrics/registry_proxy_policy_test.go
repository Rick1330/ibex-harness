package metrics

import "testing"

func TestProxyRegistry_PolicySnapshotMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("policy-snapshot-metrics-test")
	reg.IncPolicySnapshot("issued")
	reg.IncPolicySnapshot("expired")
	reg.IncPolicySnapshot("")

	families := gatherFamilies(t, reg.Gatherer())
	fam := families["ibex_proxy_policy_snapshot_total"]
	if fam == nil {
		t.Fatal("missing ibex_proxy_policy_snapshot_total")
	}
	if got := counterByLabel(fam, "result", "issued"); got != 1 {
		t.Fatalf("issued=%v", got)
	}
	if got := counterByLabel(fam, "result", "expired"); got != 1 {
		t.Fatalf("expired=%v", got)
	}
	if got := counterByLabel(fam, "result", "unknown"); got != 1 {
		t.Fatalf("empty result=%v", got)
	}
	if got := counterByLabel(fam, "result", "denied"); got != 0 {
		t.Fatalf("denied materialized=%v", got)
	}
}

func TestProxyRegistry_PolicySnapshotMetrics_NilSafe(t *testing.T) {
	t.Parallel()
	var nilReg *ProxyRegistry
	nilReg.IncPolicySnapshot("issued")
	(&ProxyRegistry{}).IncPolicySnapshot("issued")
}
