package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
)

// Relay batch result label values.
const (
	RelayBatchOK    = "ok"
	RelayBatchError = "error"
)

// Relay delivery result label values.
const (
	RelayDeliveryOK    = "ok"
	RelayDeliveryError = "error"
)

// Relay fence-check outcome label values.
const (
	RelayFenceAlive      = "alive"
	RelayFenceTombstoned = "tombstoned"
	RelayFenceStale      = "stale_version"
	RelayFenceNotFound   = "not_found"
	RelayFenceError      = "error"
)

// RelayRegistry holds Prometheus metrics for the evidence relay daemon.
type RelayRegistry struct {
	reg    prometheus.Registerer
	gather prometheus.Gatherer

	batchesTotal       *prometheus.CounterVec
	claimedTotal       prometheus.Counter
	deliveredTotal     prometheus.Counter
	retriedTotal       prometheus.Counter
	deadLetterTotal    prometheus.Counter
	recoveredTotal     prometheus.Counter
	batchDuration      prometheus.Histogram
	deliveryDuration   *prometheus.HistogramVec
	fenceCheckDuration *prometheus.HistogramVec
	processUp          prometheus.Gauge
}

// NewRelay creates and registers evidence relay metrics.
func NewRelay(serviceName string) *RelayRegistry {
	reg := prometheus.NewRegistry()
	r := &RelayRegistry{reg: reg, gather: reg}
	r.register(serviceName)
	return r
}

func (r *RelayRegistry) register(serviceName string) {
	r.initCounters()
	r.initHistograms()
	r.processUp = prometheus.NewGauge(prometheus.GaugeOpts{
		Name:        "ibex_process_up",
		Help:        "1 if the service process is running.",
		ConstLabels: prometheus.Labels{"service": serviceName},
	})
	mustRegisterAll(r.reg,
		r.batchesTotal, r.claimedTotal, r.deliveredTotal, r.retriedTotal,
		r.deadLetterTotal, r.recoveredTotal, r.batchDuration, r.deliveryDuration,
		r.fenceCheckDuration, r.processUp,
	)
	r.processUp.Set(1)
}

func (r *RelayRegistry) initCounters() {
	r.batchesTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_relay_batches_total",
		Help: "Total relay batch processing runs by result.",
	}, []string{"result"})
	r.claimedTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_relay_claimed_total",
		Help: "Total outbox rows claimed for delivery.",
	})
	r.deliveredTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_relay_delivered_total",
		Help: "Total outbox rows delivered and acknowledged.",
	})
	r.retriedTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_relay_retried_total",
		Help: "Total outbox rows marked failed for retry.",
	})
	r.deadLetterTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_relay_dead_letter_total",
		Help: "Total outbox rows marked poison (dead-lettered).",
	})
	r.recoveredTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_relay_recovered_total",
		Help: "Total stale in-flight outbox rows recovered to pending.",
	})
}

func (r *RelayRegistry) initHistograms() {
	r.batchDuration = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "ibex_relay_batch_duration_seconds",
		Help:    "Relay batch processing duration in seconds.",
		Buckets: LatencyBuckets,
	})
	r.deliveryDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_relay_delivery_duration_seconds",
		Help:    "Tombstone-fenced delivery duration in seconds by result.",
		Buckets: LatencyBuckets,
	}, []string{"result"})
	r.fenceCheckDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_relay_fence_check_duration_seconds",
		Help:    "Authoritative session fence check duration in seconds by outcome.",
		Buckets: LatencyBuckets,
	}, []string{"outcome"})
}

// Gatherer returns the registry for promhttp exposition.
func (r *RelayRegistry) Gatherer() prometheus.Gatherer {
	return r.gather
}

// ObserveBatch records one batch run outcome and duration.
func (r *RelayRegistry) ObserveBatch(result string, seconds float64) {
	r.batchesTotal.WithLabelValues(boundRelayLabel(result, relayBatchResults)).Inc()
	r.batchDuration.Observe(seconds)
}

// AddClaimed records rows claimed in a batch.
func (r *RelayRegistry) AddClaimed(n int) {
	addCounter(r.claimedTotal, n)
}

// AddDelivered records rows delivered and acknowledged.
func (r *RelayRegistry) AddDelivered(n int) {
	addCounter(r.deliveredTotal, n)
}

// AddRetried records rows marked failed for retry.
func (r *RelayRegistry) AddRetried(n int) {
	addCounter(r.retriedTotal, n)
}

// AddDeadLettered records rows marked poison.
func (r *RelayRegistry) AddDeadLettered(n int) {
	addCounter(r.deadLetterTotal, n)
}

// AddRecovered records stale in-flight rows returned to pending.
func (r *RelayRegistry) AddRecovered(n int) {
	addCounter(r.recoveredTotal, n)
}

// ObserveDelivery records one tombstone-fenced delivery duration.
func (r *RelayRegistry) ObserveDelivery(result string, seconds float64) {
	r.deliveryDuration.WithLabelValues(boundRelayLabel(result, relayDeliveryResults)).Observe(seconds)
}

// ObserveFenceCheck records one authoritative fence check duration.
func (r *RelayRegistry) ObserveFenceCheck(outcome string, seconds float64) {
	r.fenceCheckDuration.WithLabelValues(boundRelayLabel(outcome, relayFenceOutcomes)).Observe(seconds)
}

var (
	relayBatchResults = map[string]struct{}{
		RelayBatchOK: {}, RelayBatchError: {},
	}
	relayDeliveryResults = map[string]struct{}{
		RelayDeliveryOK: {}, RelayDeliveryError: {},
	}
	relayFenceOutcomes = map[string]struct{}{
		RelayFenceAlive: {}, RelayFenceTombstoned: {}, RelayFenceStale: {},
		RelayFenceNotFound: {}, RelayFenceError: {},
	}
)

func boundRelayLabel(label string, allowed map[string]struct{}) string {
	if _, ok := allowed[label]; ok {
		return label
	}
	return "error"
}

func addCounter(counter prometheus.Counter, n int) {
	if n <= 0 {
		return
	}
	counter.Add(float64(n))
}
