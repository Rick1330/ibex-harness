package authcache

// Metrics records auth cache outcomes. Labels must stay low-cardinality (tier only).
type Metrics interface {
	IncAuthCacheHit(tier string)
	IncAuthCacheMiss(tier string)
	SetAuthCacheLRUSize(n float64)
	IncAuthCacheLRUEviction()
	IncAuthCacheBloomFP()
}

// NoopMetrics discards all metric updates (tests / disabled exporters).
type NoopMetrics struct{}

func (NoopMetrics) IncAuthCacheHit(string) {
	// No-op when no metrics registry is wired.
}

func (NoopMetrics) IncAuthCacheMiss(string) {
	// No-op when no metrics registry is wired.
}

func (NoopMetrics) SetAuthCacheLRUSize(float64) {
	// No-op when no metrics registry is wired.
}

func (NoopMetrics) IncAuthCacheLRUEviction() {
	// No-op when no metrics registry is wired.
}

func (NoopMetrics) IncAuthCacheBloomFP() {
	// No-op when no metrics registry is wired.
}
