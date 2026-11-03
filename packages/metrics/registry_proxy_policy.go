package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initPolicySnapshotMetrics() {
	r.policySnapshotTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_policy_snapshot_total",
		Help: "Policy snapshot issuance/verification outcomes by result label.",
	}, []string{"result"})
}

// IncPolicySnapshot records one policy snapshot outcome.
// result is a stable label (issued, denied, invalid_token, expired,
// org_mismatch, agent_mismatch, key_unknown, signature_invalid, unavailable);
// never org, agent, or claim content.
func (r *ProxyRegistry) IncPolicySnapshot(result string) {
	if r == nil || r.policySnapshotTotal == nil {
		return
	}
	if result == "" {
		result = "unknown"
	}
	r.policySnapshotTotal.WithLabelValues(result).Inc()
}
