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
	processUp             prometheus.Gauge
}

func buildAuthMetricSet(serviceName string) authMetricSet {
	return authMetricSet{
		validateTokenDuration: newValidateTokenHistogram(),
		validateAgentDuration: newValidateAgentHistogram(),
		grpcRequestsTotal:     newGRPCRequestsCounter(),
		dbQueryDuration:       newDBQueryHistogram(),
		processUp:             newProcessUpGauge(serviceName),
	}
}

func authCollectors(set authMetricSet, db *sql.DB) []prometheus.Collector {
	out := []prometheus.Collector{
		set.validateTokenDuration,
		set.validateAgentDuration,
		set.grpcRequestsTotal,
		set.dbQueryDuration,
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

func newProcessUpGauge(serviceName string) prometheus.Gauge {
	return prometheus.NewGauge(prometheus.GaugeOpts{
		Name:        "ibex_process_up",
		Help:        "1 if the service process is running.",
		ConstLabels: prometheus.Labels{"service": serviceName},
	})
}
