package metrics

import (
	"database/sql"

	"github.com/prometheus/client_golang/prometheus"
)

// AuthRegistry holds Prometheus metrics for the auth service.
type AuthRegistry struct {
	reg    prometheus.Registerer
	gather prometheus.Gatherer

	validateTokenDuration *prometheus.HistogramVec
	validateAgentDuration *prometheus.HistogramVec
	grpcRequestsTotal     *prometheus.CounterVec
	dbQueryDuration       *prometheus.HistogramVec
	processUp             prometheus.Gauge
}

// NewAuth creates and registers auth metrics. db may be nil (skips pool collector).
func NewAuth(serviceName string, db *sql.DB) *AuthRegistry {
	reg := prometheus.NewRegistry()
	r := &AuthRegistry{reg: reg, gather: reg}
	r.register(serviceName, db)
	return r
}

func (r *AuthRegistry) register(serviceName string, db *sql.DB) {
	r.validateTokenDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_auth_validate_token_duration_seconds",
		Help:    "Auth gRPC ValidateToken call duration.",
		Buckets: LatencyBuckets,
	}, []string{"result"})

	r.validateAgentDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_auth_validate_agent_duration_seconds",
		Help:    "Auth gRPC ValidateAgent call duration.",
		Buckets: LatencyBuckets,
	}, []string{"result"})

	r.grpcRequestsTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ibex_auth_grpc_requests_total",
		Help: "Auth gRPC call outcomes.",
	}, []string{"method", "status"})

	r.dbQueryDuration = prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "ibex_db_query_duration_seconds",
		Help:    "Database query duration.",
		Buckets: LatencyBuckets,
	}, []string{"operation"})

	r.processUp = prometheus.NewGauge(prometheus.GaugeOpts{
		Name:        "ibex_process_up",
		Help:        "1 if the service process is running.",
		ConstLabels: prometheus.Labels{"service": serviceName},
	})

	collectors := []prometheus.Collector{
		r.validateTokenDuration,
		r.validateAgentDuration,
		r.grpcRequestsTotal,
		r.dbQueryDuration,
		r.processUp,
	}
	if db != nil {
		collectors = append(collectors, newDBPoolCollector(db))
	}
	mustRegisterAll(r.reg, collectors...)
	r.processUp.Set(1)
}

// Gatherer returns the registry for promhttp exposition.
func (r *AuthRegistry) Gatherer() prometheus.Gatherer {
	return r.gather
}

// ObserveValidateToken records ValidateToken duration.
func (r *AuthRegistry) ObserveValidateToken(result string, seconds float64) {
	r.validateTokenDuration.WithLabelValues(result).Observe(seconds)
}

// ObserveValidateAgent records ValidateAgent duration.
func (r *AuthRegistry) ObserveValidateAgent(result string, seconds float64) {
	r.validateAgentDuration.WithLabelValues(result).Observe(seconds)
}

// IncGRPCRequest records a gRPC method outcome.
func (r *AuthRegistry) IncGRPCRequest(method, status string) {
	r.grpcRequestsTotal.WithLabelValues(method, status).Inc()
}

// ObserveDBQuery records database query duration.
func (r *AuthRegistry) ObserveDBQuery(operation string, seconds float64) {
	r.dbQueryDuration.WithLabelValues(operation).Observe(seconds)
}
