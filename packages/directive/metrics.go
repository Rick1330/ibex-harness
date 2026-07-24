package directive

// Metrics records directive resolve outcomes (low-cardinality labels only).
type Metrics interface {
	IncDirectiveCacheHit()
	IncDirectiveCacheMiss()
	IncDirectiveResolveError()
	ObserveDirectiveResolveSeconds(seconds float64)
	IncDirectiveInvalidate()
}

// NoopMetrics discards metric updates when Prometheus is not wired.
type NoopMetrics struct{}

// IncDirectiveCacheHit is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncDirectiveCacheHit() {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// IncDirectiveCacheMiss is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncDirectiveCacheMiss() {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// IncDirectiveResolveError is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncDirectiveResolveError() {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// ObserveDirectiveResolveSeconds is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) ObserveDirectiveResolveSeconds(float64) {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// IncDirectiveInvalidate is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncDirectiveInvalidate() {
	// No-op: metrics sink unused in tests / when registry is nil.
}
