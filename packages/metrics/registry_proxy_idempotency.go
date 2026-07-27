package metrics

import "github.com/prometheus/client_golang/prometheus"

// IdempotencyHit counts completed-key replays (no second provider call).
const IdempotencyHit = "hit"

// IdempotencyMiss counts first claims that own the in-flight key.
const IdempotencyMiss = "miss"

// IdempotencyConflict counts same-key requests with a different fingerprint.
const IdempotencyConflict = "conflict"

// IdempotencyInProgress counts requests rejected while another claim is pending.
const IdempotencyInProgress = "in_progress"

// IdempotencyRedisError counts Redis failures or unknown result labels (fail-open path).
const IdempotencyRedisError = "redis_error"

// IdempotencySkipped counts requests with no Idempotency-Key or no store configured.
const IdempotencySkipped = "skipped"

func (r *ProxyRegistry) initIdempotencyMetrics() {
	r.idempotencyTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_idempotency_total",
		Help: "Idempotency-Key claim outcomes for chat completions.",
	}, []string{"result"})
	r.idempotencyDuration = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_proxy_idempotency_duration_seconds",
		Help:    "Redis claim/commit wall time for Idempotency-Key handling.",
		Buckets: LatencyBuckets,
	})
	for _, result := range []string{
		IdempotencyHit, IdempotencyMiss, IdempotencyConflict,
		IdempotencyInProgress, IdempotencyRedisError, IdempotencySkipped,
	} {
		r.idempotencyTotal.WithLabelValues(result)
	}
}

// IncIdempotency records an idempotency claim outcome.
// Aggregate proxy metric only — never label by org/key.
func (r *ProxyRegistry) IncIdempotency(result string) {
	if r == nil || r.idempotencyTotal == nil {
		return
	}
	r.idempotencyTotal.WithLabelValues(boundIdempotencyResult(result)).Inc()
}

// ObserveIdempotencyDurationSeconds records Redis claim/commit wall time.
func (r *ProxyRegistry) ObserveIdempotencyDurationSeconds(seconds float64) {
	if r == nil || r.idempotencyDuration == nil {
		return
	}
	r.idempotencyDuration.Observe(seconds)
}

func boundIdempotencyResult(result string) string {
	switch result {
	case IdempotencyHit, IdempotencyMiss, IdempotencyConflict,
		IdempotencyInProgress, IdempotencyRedisError, IdempotencySkipped:
		return result
	default:
		return IdempotencyRedisError
	}
}
