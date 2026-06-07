package metrics

import (
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

// NewAuth creates and registers auth metrics. DB may be nil (skips pool collector).
func NewAuth(cfg AuthConfig) *AuthRegistry {
	reg := prometheus.NewRegistry()
	set := buildAuthMetricSet(cfg.ServiceName)
	mustRegisterAll(reg, authCollectors(set, cfg.DB)...)
	r := &AuthRegistry{
		reg:                   reg,
		gather:                reg,
		validateTokenDuration: set.validateTokenDuration,
		validateAgentDuration: set.validateAgentDuration,
		grpcRequestsTotal:     set.grpcRequestsTotal,
		dbQueryDuration:       set.dbQueryDuration,
		processUp:             set.processUp,
	}
	r.processUp.Set(1)
	return r
}

// Gatherer returns the registry for promhttp exposition.
func (r *AuthRegistry) Gatherer() prometheus.Gatherer {
	return r.gather
}

// ObserveValidateToken records ValidateToken duration.
func (r *AuthRegistry) ObserveValidateToken(result TokenValidateResult, seconds float64) {
	r.validateTokenDuration.WithLabelValues(string(result)).Observe(seconds)
}

// ObserveValidateAgent records ValidateAgent duration.
func (r *AuthRegistry) ObserveValidateAgent(result AgentValidateResult, seconds float64) {
	r.validateAgentDuration.WithLabelValues(string(result)).Observe(seconds)
}

// IncGRPCRequest records a gRPC method outcome.
func (r *AuthRegistry) IncGRPCRequest(labels GRPCRequestLabels) {
	r.grpcRequestsTotal.WithLabelValues(labels.Method, labels.Status).Inc()
}

// ObserveDBQuery records database query duration.
func (r *AuthRegistry) ObserveDBQuery(op DBOperation, seconds float64) {
	r.dbQueryDuration.WithLabelValues(string(op)).Observe(seconds)
}
