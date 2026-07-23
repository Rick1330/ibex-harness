package metrics

import (
	"database/sql"

	"github.com/prometheus/client_golang/prometheus"
)

type authMetricSet struct {
	validateTokenDuration *prometheus.HistogramVec
	validateAgentDuration *prometheus.HistogramVec
	grpcRequestsTotal     *prometheus.CounterVec
	dbQueryDuration       *prometheus.HistogramVec
	httpRequestDuration   *prometheus.HistogramVec
	httpRequestsTotal     *prometheus.CounterVec
	revocationPublish     *prometheus.CounterVec
	processUp             prometheus.Gauge
}

func buildAuthMetricSet(serviceName string) authMetricSet {
	set := authMetricSet{
		validateTokenDuration: newValidateTokenHistogram(),
		validateAgentDuration: newValidateAgentHistogram(),
		grpcRequestsTotal:     newGRPCRequestsCounter(),
		dbQueryDuration:       newDBQueryHistogram(),
		httpRequestDuration:   newAuthHTTPRequestHistogram(),
		httpRequestsTotal:     newAuthHTTPRequestsCounter(),
		revocationPublish:     newAuthRevocationPublishCounter(),
		processUp:             newProcessUpGauge(serviceName),
	}
	set.revocationPublish.WithLabelValues("ok")
	set.revocationPublish.WithLabelValues("error")
	return set
}

func authCollectors(set authMetricSet, db *sql.DB) []prometheus.Collector {
	out := []prometheus.Collector{
		set.validateTokenDuration,
		set.validateAgentDuration,
		set.grpcRequestsTotal,
		set.dbQueryDuration,
		set.httpRequestDuration,
		set.httpRequestsTotal,
		set.revocationPublish,
		set.processUp,
	}
	if db != nil {
		out = append(out, newDBPoolCollector(db))
	}
	return out
}

func newValidateTokenHistogram() *prometheus.HistogramVec {
	return prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_auth_validate_token_duration_seconds",
		Help:    "Auth gRPC ValidateToken call duration.",
		Buckets: LatencyBuckets,
	}, []string{"result"})
}

func newValidateAgentHistogram() *prometheus.HistogramVec {
	return prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_auth_validate_agent_duration_seconds",
		Help:    "Auth gRPC ValidateAgent call duration.",
		Buckets: LatencyBuckets,
	}, []string{"result"})
}

func newGRPCRequestsCounter() *prometheus.CounterVec {
	return prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_auth_grpc_requests_total",
		Help: "Auth gRPC call outcomes.",
	}, []string{"method", "status"})
}

func newDBQueryHistogram() *prometheus.HistogramVec {
	return prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_db_query_duration_seconds",
		Help:    "Database query duration.",
		Buckets: LatencyBuckets,
	}, []string{"operation"})
}

func newAuthHTTPRequestHistogram() *prometheus.HistogramVec {
	return prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_auth_http_request_duration_seconds",
		Help:    "Auth HTTP request duration.",
		Buckets: LatencyBuckets,
	}, []string{"route", "method", "status_code"})
}

func newAuthHTTPRequestsCounter() *prometheus.CounterVec {
	return prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_auth_http_requests_total",
		Help: "Total HTTP requests to auth service.",
	}, []string{"route", "method", "status_code"})
}

func newAuthRevocationPublishCounter() *prometheus.CounterVec {
	return prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_auth_revocation_publish_total",
		Help: "Token revocation Redis PUBLISH outcomes.",
	}, []string{"result"})
}

func newProcessUpGauge(serviceName string) prometheus.Gauge {
	return prometheus.NewGauge(prometheus.GaugeOpts{
		Name:        "ibex_process_up",
		Help:        "1 if the service process is running.",
		ConstLabels: prometheus.Labels{"service": serviceName},
	})
}
