package metrics

import "github.com/prometheus/client_golang/prometheus"

func (r *ProxyRegistry) register(serviceName string) {
	r.initHTTPMetrics()
	r.initRateLimitMetrics()
	r.initProviderMetrics()
	r.initStreamMetrics()
	r.initAsyncMetrics()
	r.initAuthCacheMetrics()
	r.initRevocationMetrics()
	r.initDirectiveMetrics()
	r.initSessionMetrics()
	r.initClickHouseMetrics()
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
		r.authCacheHits,
		r.authCacheMisses,
		r.authCacheLRUSize,
		r.authCacheLRUEvict,
		r.authCacheBloomFP,
		r.revocationInvalidate,
		r.directiveCacheHits,
		r.directiveCacheMisses,
		r.directiveResolveErrs,
		r.directiveResolveSec,
		r.directiveInvalidate,
		r.sessionGetOrCreate,
		r.sessionGetOrCreateSec,
		r.sessionCheckpoint,
		r.sessionComplete,
		r.sessionSweeperMarked,
		r.sessionSweeperRuns,
		r.clickhouseFlushTotal,
		r.clickhouseFlushRows,
		r.clickhouseFlushSec,
		r.processUp,
	)
	r.processUp.Set(1)
}

func (r *ProxyRegistry) initHTTPMetrics() {
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
}

func (r *ProxyRegistry) initRateLimitMetrics() {
	r.rateLimitedTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_rate_limited_total",
		Help: "Rate limit check outcomes.",
	}, []string{"result"})
	r.rateLimitRedisErrors = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_rate_limit_redis_errors_total",
		Help: "Redis failures during rate limiting.",
	})
}

func (r *ProxyRegistry) initProviderMetrics() {
	r.providerRequests = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_provider_requests_total",
		Help: "Upstream LLM provider HTTP outcomes.",
	}, []string{"provider", "status_class"})
	r.providerRetries = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_proxy_provider_retries_total",
		Help: "Upstream LLM provider retry attempts.",
	}, []string{"provider"})
}

func (r *ProxyRegistry) initStreamMetrics() {
	r.streamDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_proxy_stream_duration_seconds",
		Help:    "Duration of SSE stream forward from response headers through copy completion.",
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
}

func (r *ProxyRegistry) initAsyncMetrics() {
	r.asyncQueueDepth = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ibex_proxy_async_queue_depth",
		Help: "Current depth of the proxy post-response async work queue.",
	})
	r.asyncDroppedTotal = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ibex_proxy_async_dropped_total",
		Help: "Post-response async tasks dropped when a telemetry queue is full.",
	})
}
