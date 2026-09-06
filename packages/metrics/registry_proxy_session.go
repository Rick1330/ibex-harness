package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) initSessionMetrics() {
	r.sessionGetOrCreate = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_session_get_or_create_total",
		Help: "Session GetOrCreate outcomes.",
	}, []string{"result"})
	r.sessionGetOrCreateSec = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_proxy_session_get_or_create_duration_seconds",
		Help:    "Session GetOrCreate latency.",
		Buckets: LatencyBuckets,
	})
	r.sessionCheckpoint = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_session_checkpoint_total",
		Help: "Session AppendCheckpoint outcomes.",
	}, []string{"result"})
	r.sessionComplete = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_session_complete_total",
		Help: "Session Complete outcomes.",
	}, []string{"result"})
	r.sessionSweeperMarked = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_session_sweeper_marked_total",
		Help: "Sessions marked by the idle-timeout sweeper.",
	}, []string{"status"})
	r.sessionSweeperRuns = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_session_sweeper_runs_total",
		Help: "Idle-timeout sweeper tick outcomes.",
	}, []string{"result"})
	// Materialize bounded result series at init (no first-hit registration).
	for _, result := range []string{"created", "existing", "error"} {
		r.sessionGetOrCreate.WithLabelValues(result)
	}
	for _, result := range []string{"ok", "duplicate", "error"} {
		r.sessionCheckpoint.WithLabelValues(result)
	}
	for _, result := range []string{"ok", "noop", "not_found", "error"} {
		r.sessionComplete.WithLabelValues(result)
	}
	r.sessionSweeperMarked.WithLabelValues("abandoned")
	r.sessionSweeperMarked.WithLabelValues("error")
	for _, result := range []string{"ok", "error", "skipped_lock", "noop"} {
		r.sessionSweeperRuns.WithLabelValues(result)
	}
}

// IncSessionGetOrCreate records a GetOrCreate outcome (created|existing|error).
func (r *ProxyRegistry) IncSessionGetOrCreate(result string) {
	r.sessionGetOrCreate.WithLabelValues(boundSessionResult(result, sessionGetOrCreateResults)).Inc()
}

// ObserveSessionGetOrCreateSeconds records GetOrCreate wall time.
func (r *ProxyRegistry) ObserveSessionGetOrCreateSeconds(seconds float64) {
	r.sessionGetOrCreateSec.Observe(seconds)
}

// IncSessionCheckpoint records an AppendCheckpoint outcome (ok|duplicate|error).
func (r *ProxyRegistry) IncSessionCheckpoint(result string) {
	r.sessionCheckpoint.WithLabelValues(boundSessionResult(result, sessionCheckpointResults)).Inc()
}

// IncSessionComplete records a Complete outcome (ok|noop|not_found|error).
func (r *ProxyRegistry) IncSessionComplete(result string) {
	r.sessionComplete.WithLabelValues(boundSessionResult(result, sessionCompleteResults)).Inc()
}

// IncSessionSweeperMarked records a session marked by the idle sweeper.
// Unsupported status values are normalized to "error" before recording;
// callers should use the bounded label set (e.g. "abandoned").
func (r *ProxyRegistry) IncSessionSweeperMarked(status string) {
	r.sessionSweeperMarked.WithLabelValues(boundSessionResult(status, sessionSweeperMarkedStatuses)).Inc()
}

// IncSessionSweeperRun records a sweeper tick outcome.
// Unsupported result values are normalized to "error" before recording;
// callers should use ok|error|skipped_lock|noop.
func (r *ProxyRegistry) IncSessionSweeperRun(result string) {
	r.sessionSweeperRuns.WithLabelValues(boundSessionResult(result, sessionSweeperRunResults)).Inc()
}

var (
	sessionGetOrCreateResults = map[string]struct{}{
		"created": {}, "existing": {}, "error": {},
	}
	sessionCheckpointResults = map[string]struct{}{
		"ok": {}, "duplicate": {}, "error": {},
	}
	sessionCompleteResults = map[string]struct{}{
		"ok": {}, "noop": {}, "not_found": {}, "error": {},
	}
	sessionSweeperMarkedStatuses = map[string]struct{}{
		"abandoned": {}, "error": {},
	}
	sessionSweeperRunResults = map[string]struct{}{
		"ok": {}, "error": {}, "skipped_lock": {}, "noop": {},
	}
)

func boundSessionResult(result string, allowed map[string]struct{}) string {
	if _, ok := allowed[result]; ok {
		return result
	}
	return "error"
}
