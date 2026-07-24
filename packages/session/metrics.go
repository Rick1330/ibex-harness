package session

// Metrics records session store outcomes (low-cardinality labels only).
type Metrics interface {
	IncSessionGetOrCreate(result string)
	ObserveSessionGetOrCreateSeconds(seconds float64)
	IncSessionCheckpoint(result string)
	IncSessionComplete(result string)
}

// NoopMetrics discards metric updates when Prometheus is not wired.
type NoopMetrics struct{}

// IncSessionGetOrCreate is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncSessionGetOrCreate(string) {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// ObserveSessionGetOrCreateSeconds is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) ObserveSessionGetOrCreateSeconds(float64) {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// IncSessionCheckpoint is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncSessionCheckpoint(string) {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// IncSessionComplete is intentionally empty: no Prometheus registry attached.
func (NoopMetrics) IncSessionComplete(string) {
	// No-op: metrics sink unused in tests / when registry is nil.
}

// Bounded result label values for session metrics.
const (
	ResultCreated   = "created"
	ResultExisting  = "existing"
	ResultOK        = "ok"
	ResultDuplicate = "duplicate"
	ResultNoop      = "noop"
	ResultError     = "error"
)
