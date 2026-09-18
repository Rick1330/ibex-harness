package billing

// Metrics records budget cache counters.
type Metrics interface {
	IncCacheHit(tier string)
	IncCacheMiss(tier string)
	IncDeny()
	IncInvalidate()
	SetLRUSize(n float64)
}

// NoopMetrics discards metrics.
type NoopMetrics struct{}

func (NoopMetrics) IncCacheHit(string)  {}
func (NoopMetrics) IncCacheMiss(string) {}
func (NoopMetrics) IncDeny()            {}
func (NoopMetrics) IncInvalidate()      {}
func (NoopMetrics) SetLRUSize(float64)  {}
