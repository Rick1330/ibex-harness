package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initAuthDurationMetrics() {
	r.authDuration = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_proxy_auth_duration_seconds",
		Help:    "Proxy auth middleware wall time (parse + validate + authorize).",
		Buckets: LatencyBuckets,
	})
}

// ObserveAuthDurationSeconds records auth middleware wall time in seconds
// (parse + validate + authorize, excluding downstream handlers). A nil
// receiver or uninitialized registry is a no-op.
func (r *ProxyRegistry) ObserveAuthDurationSeconds(seconds float64) {
	if r == nil || r.authDuration == nil {
		return
	}
	r.authDuration.Observe(seconds)
}
