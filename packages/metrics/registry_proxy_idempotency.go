package metrics

import "github.com/prometheus/client_golang/prometheus"

// Idempotency result labels for ibex_proxy_idempotency_total.
const (
	IdempotencyHit        = "hit"
	IdempotencyMiss       = "miss"
	IdempotencyConflict   = "conflict"
	IdempotencyInProgress = "in_progress"
	IdempotencyRedisError = "redis_error"
	IdempotencySkipped    = "skipped"
)

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

var idempotencyResults = map[string]struct{}{
	IdempotencyHit: {}, IdempotencyMiss: {}, IdempotencyConflict: {},
	IdempotencyInProgress: {}, IdempotencyRedisError: {}, IdempotencySkipped: {},
}

func boundIdempotencyResult(result string) string {
	if _, ok := idempotencyResults[result]; ok {
		return result
	}
	return IdempotencyRedisError
}
