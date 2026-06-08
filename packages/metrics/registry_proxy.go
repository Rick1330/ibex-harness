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

func mustRegisterAll(reg prometheus.Registerer, collectors ...prometheus.Collector) {
	for _, c := range collectors {
		reg.MustRegister(c)
	}
}
