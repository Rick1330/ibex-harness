package metrics

// LatencyBuckets are the standard histogram buckets for all latency measurements
// in IBEX Harness. Tuned for the <20ms proxy overhead target.
var LatencyBuckets = []float64{
	0.001, 0.005, 0.010, 0.020, 0.050,
	0.100, 0.250, 0.500, 1.000, 5.000,
}
