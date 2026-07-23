package metrics

// ProxyRequiredMetricNames lists metrics that must appear on proxy /metrics.
var ProxyRequiredMetricNames = []string{
	"ibex_proxy_request_duration_seconds",
	"ibex_proxy_requests_total",
	"ibex_proxy_active_connections",
	"ibex_proxy_rate_limited_total",
	"ibex_proxy_rate_limit_redis_errors_total",
	"ibex_proxy_stream_duration_seconds",
	"ibex_proxy_stream_client_disconnects_total",
	"ibex_proxy_stream_upstream_disconnects_total",
	"ibex_proxy_stream_backpressure_events_total",
	"ibex_proxy_async_queue_depth",
	"ibex_proxy_async_dropped_total",
	"ibex_proxy_auth_cache_hits_total",
	"ibex_proxy_auth_cache_misses_total",
	"ibex_proxy_auth_cache_lru_size",
	"ibex_proxy_auth_cache_lru_evictions_total",
	"ibex_proxy_auth_cache_bloom_fp_total",
	"ibex_process_up",
}

// AuthRequiredMetricNames lists metrics that must appear on auth /metrics.
var AuthRequiredMetricNames = []string{
	"ibex_auth_validate_token_duration_seconds",
	"ibex_auth_validate_agent_duration_seconds",
	"ibex_auth_grpc_requests_total",
	"ibex_db_query_duration_seconds",
	"ibex_db_pool_open_connections",
	"ibex_auth_http_request_duration_seconds",
	"ibex_auth_http_requests_total",
	"ibex_process_up",
}

// ForbiddenLabelNames must never appear on registered metrics.
var ForbiddenLabelNames = []string{
	"org_id",
	"agent_id",
	"user_id",
	"session_id",
}
