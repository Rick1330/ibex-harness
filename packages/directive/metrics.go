package directive

// Metrics records directive resolve outcomes (low-cardinality labels only).
type Metrics interface {
	IncDirectiveCacheHit()
	IncDirectiveCacheMiss()
	IncDirectiveResolveError()
	ObserveDirectiveResolveSeconds(seconds float64)
	IncDirectiveInvalidate()
}

// NoopMetrics discards metric updates.
type NoopMetrics struct{}

// IncDirectiveCacheHit implements Metrics.
func (NoopMetrics) IncDirectiveCacheHit() {}

// IncDirectiveCacheMiss implements Metrics.
func (NoopMetrics) IncDirectiveCacheMiss() {}

// IncDirectiveResolveError implements Metrics.
func (NoopMetrics) IncDirectiveResolveError() {}

// ObserveDirectiveResolveSeconds implements Metrics.
func (NoopMetrics) ObserveDirectiveResolveSeconds(float64) {}

// IncDirectiveInvalidate implements Metrics.
func (NoopMetrics) IncDirectiveInvalidate() {}
