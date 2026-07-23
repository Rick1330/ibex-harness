package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
)

// ProxyRegistry holds Prometheus metrics for the proxy service.
type ProxyRegistry struct {
	reg    prometheus.Registerer
	gather prometheus.Gatherer

	requestDuration      *prometheus.HistogramVec
	requestsTotal        *prometheus.CounterVec
	activeConnections    prometheus.Gauge
	rateLimitedTotal     *prometheus.CounterVec
	rateLimitRedisErrors prometheus.Counter
	providerRequests     *prometheus.CounterVec
	providerRetries      *prometheus.CounterVec
	streamDuration       *prometheus.HistogramVec
	streamClientDisc     prometheus.Counter
	streamUpstreamDisc   prometheus.Counter
	streamBackpressure   prometheus.Counter
	asyncQueueDepth      prometheus.Gauge
	asyncDroppedTotal    prometheus.Counter
	authCacheHits        *prometheus.CounterVec
	authCacheMisses      *prometheus.CounterVec
	authCacheLRUSize     prometheus.Gauge
	authCacheLRUEvict    prometheus.Counter
	authCacheBloomFP     prometheus.Counter
	processUp            prometheus.Gauge
}

// NewProxy creates and registers proxy metrics.
func NewProxy(serviceName string) *ProxyRegistry {
	reg := prometheus.NewRegistry()
	r := &ProxyRegistry{reg: reg, gather: reg}
	r.register(serviceName)
	return r
}

// Gatherer returns the registry for promhttp exposition.
func (r *ProxyRegistry) Gatherer() prometheus.Gatherer {
	return r.gather
}

// ObserveHTTPRequest records proxy request count and duration.
func (r *ProxyRegistry) ObserveHTTPRequest(obs HTTPRequestObservation) {
	r.requestsTotal.WithLabelValues(obs.Route, obs.Method, obs.StatusCode).Inc()
	r.requestDuration.WithLabelValues(obs.Route, obs.Method, obs.StatusCode).Observe(obs.Seconds)
}

// IncActiveConnection increments in-flight connection gauge.
func (r *ProxyRegistry) IncActiveConnection() {
	r.activeConnections.Inc()
}

// DecActiveConnection decrements in-flight connection gauge.
func (r *ProxyRegistry) DecActiveConnection() {
	r.activeConnections.Dec()
}

// IncRateLimitAllowed records an allowed rate-limit check.
func (r *ProxyRegistry) IncRateLimitAllowed() {
	r.rateLimitedTotal.WithLabelValues(RateLimitAllowed).Inc()
}

// IncRateLimitDenied records a denied rate-limit check.
func (r *ProxyRegistry) IncRateLimitDenied() {
	r.rateLimitedTotal.WithLabelValues(RateLimitDenied).Inc()
}

// IncRateLimitRedisError records a Redis failure during rate limiting.
func (r *ProxyRegistry) IncRateLimitRedisError() {
	r.rateLimitRedisErrors.Inc()
}

// IncProviderRequest records an upstream provider HTTP outcome.
func (r *ProxyRegistry) IncProviderRequest(provider, statusClass string) {
	r.providerRequests.WithLabelValues(provider, statusClass).Inc()
}

// IncProviderRetry records an upstream provider retry attempt.
func (r *ProxyRegistry) IncProviderRetry(provider string) {
	r.providerRetries.WithLabelValues(provider).Inc()
}

// ObserveStreamDuration records SSE forward duration.
func (r *ProxyRegistry) ObserveStreamDuration(obs StreamObservation) {
	r.streamDuration.WithLabelValues(obs.Provider, obs.Status).Observe(obs.Seconds)
}

// IncStreamClientDisconnect records a client disconnect mid-stream.
func (r *ProxyRegistry) IncStreamClientDisconnect() {
	r.streamClientDisc.Inc()
}

// IncStreamUpstreamDisconnect records an upstream disconnect before [DONE].
func (r *ProxyRegistry) IncStreamUpstreamDisconnect() {
	r.streamUpstreamDisc.Inc()
}

// IncStreamBackpressure records a slow client write during SSE forward.
func (r *ProxyRegistry) IncStreamBackpressure() {
	r.streamBackpressure.Inc()
}

// SetAsyncQueueDepth records the current post-response async queue depth.
func (r *ProxyRegistry) SetAsyncQueueDepth(depth float64) {
	r.asyncQueueDepth.Set(depth)
}

// IncAsyncDropped records a dropped post-response telemetry task.
func (r *ProxyRegistry) IncAsyncDropped() {
	r.asyncDroppedTotal.Inc()
}

func mustRegisterAll(reg prometheus.Registerer, collectors ...prometheus.Collector) {
	for _, c := range collectors {
		reg.MustRegister(c)
	}
}
