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
	processUp            prometheus.Gauge
}

// NewProxy creates and registers proxy metrics.
func NewProxy(serviceName string) *ProxyRegistry {
	reg := prometheus.NewRegistry()
	r := &ProxyRegistry{reg: reg, gather: reg}
	r.register(serviceName)
	return r
}

func (r *ProxyRegistry) register(serviceName string) {
	r.requestDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_proxy_request_duration_seconds",
		Help:    "End-to-end proxy HTTP request duration.",
		Buckets: LatencyBuckets,
	}, []string{"route", "method", "status_code"})

	r.requestsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_requests_total",
		Help: "Total HTTP requests to the proxy.",
	}, []string{"route", "method", "status_code"})

	r.activeConnections = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ibex_proxy_active_connections",
		Help: "Currently open HTTP connections being served.",
	})

	r.rateLimitedTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_rate_limited_total",
		Help: "Rate limit check outcomes.",
	}, []string{"result"})

	r.rateLimitRedisErrors = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_rate_limit_redis_errors_total",
		Help: "Redis failures during rate limiting.",
	})

	r.providerRequests = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_provider_requests_total",
		Help: "Upstream LLM provider HTTP outcomes.",
	}, []string{"provider", "status_class"})

	r.providerRetries = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_provider_retries_total",
		Help: "Upstream LLM provider retry attempts.",
	}, []string{"provider"})

	r.streamDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_proxy_stream_duration_seconds",
		Help:    "Duration of SSE stream forward after first byte.",
		Buckets: LatencyBuckets,
	}, []string{"provider", "status"})

	r.streamClientDisc = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_stream_client_disconnects_total",
		Help: "Client disconnects mid-SSE stream.",
	})

	r.streamUpstreamDisc = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_stream_upstream_disconnects_total",
		Help: "Upstream disconnects mid-SSE stream before [DONE].",
	})

	r.streamBackpressure = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_stream_backpressure_events_total",
		Help: "Slow client write/flush events during SSE forward.",
	})

	r.asyncQueueDepth = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ibex_proxy_async_queue_depth",
		Help: "Current depth of the proxy post-response async work queue.",
	})

	r.asyncDroppedTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_async_dropped_total",
		Help: "Post-response async tasks dropped when a telemetry queue is full.",
	})

	r.processUp = prometheus.NewGauge(prometheus.GaugeOpts{
		Name:        "ibex_process_up",
		Help:        "1 if the service process is running.",
		ConstLabels: prometheus.Labels{"service": serviceName},
	})

	mustRegisterAll(r.reg,
		r.requestDuration,
		r.requestsTotal,
		r.activeConnections,
		r.rateLimitedTotal,
		r.rateLimitRedisErrors,
		r.providerRequests,
		r.providerRetries,
		r.streamDuration,
		r.streamClientDisc,
		r.streamUpstreamDisc,
		r.streamBackpressure,
		r.asyncQueueDepth,
		r.asyncDroppedTotal,
		r.processUp,
	)
	r.processUp.Set(1)
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
func (r *ProxyRegistry) ObserveStreamDuration(provider, status string, seconds float64) {
	r.streamDuration.WithLabelValues(provider, status).Observe(seconds)
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
