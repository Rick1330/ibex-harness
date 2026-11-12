package metrics

// LatencyBuckets are the standard histogram buckets for all latency measurements
// in IBEX Harness. Tuned for the <20ms proxy overhead target.
var LatencyBuckets = []float64{
	0.001, 0.005, 0.010, 0.020, 0.050,
	0.100, 0.250, 0.500, 1.000, 5.000,
}

// ProxyEnforcementBuckets are the histogram buckets for in-proxy enforcement
// work that excludes provider time: ibex_proxy_overhead_seconds (ratified SLO
// p99 <= 20 ms) and ibex_proxy_context_assemble_seconds (target p95 <= 50 ms).
//
// It is a distinct family, not a copy of LatencyBuckets: LatencyBuckets has no
// 2.5 ms, 2.5 s or 10 s bound, so a 20 ms p99 would be readable only from the
// single 20 ms boundary and a stalled call would land in the +Inf bucket. The
// bounds here resolve 1, 2.5, 5, 10 and 20 ms individually (the region the SLO
// is decided in) and still terminate at 10 s. Extend this family rather than
// adding a third one.
var ProxyEnforcementBuckets = []float64{
	0.001, 0.0025, 0.005, 0.010, 0.020, 0.050, 0.100,
	0.250, 0.500, 1.000, 2.500, 5.000, 10.000,
}
