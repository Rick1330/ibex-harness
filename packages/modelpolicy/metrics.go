package modelpolicy

// Metrics records model-policy cache and gate counters.
type Metrics interface {
	IncCacheHit(tier string)
	IncCacheMiss(tier string)
	IncDeny()
	IncInvalidate()
	SetLRUSize(n float64)
}

// NoopMetrics discards metrics.
type NoopMetrics struct{}

// IncCacheHit is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncCacheHit(string) {
	// intentionally empty: no Prometheus registry attached
}

// IncCacheMiss is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncCacheMiss(string) {
	// intentionally empty: no Prometheus registry attached
}

// IncDeny is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncDeny() {
	// intentionally empty: no Prometheus registry attached
}

// IncInvalidate is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncInvalidate() {
	// intentionally empty: no Prometheus registry attached
}

// SetLRUSize is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) SetLRUSize(float64) {
	// intentionally empty: no Prometheus registry attached
}
