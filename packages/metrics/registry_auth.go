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
	httpRequestDuration   *prometheus.HistogramVec
	httpRequestsTotal     *prometheus.CounterVec
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
		httpRequestDuration:   set.httpRequestDuration,
		httpRequestsTotal:     set.httpRequestsTotal,
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
func (r *AuthRegistry) ObserveValidateToken(obs ValidateTokenObservation) {
	r.validateTokenDuration.WithLabelValues(string(obs.Result)).Observe(obs.Seconds)
}

// ObserveValidateAgent records ValidateAgent duration.
func (r *AuthRegistry) ObserveValidateAgent(obs ValidateAgentObservation) {
	r.validateAgentDuration.WithLabelValues(string(obs.Result)).Observe(obs.Seconds)
}

// IncGRPCRequest records a gRPC method outcome.
func (r *AuthRegistry) IncGRPCRequest(labels GRPCRequestLabels) {
	r.grpcRequestsTotal.WithLabelValues(labels.Method, labels.Status).Inc()
}

// ObserveDBQuery records database query duration.
func (r *AuthRegistry) ObserveDBQuery(obs DBQueryObservation) {
	r.dbQueryDuration.WithLabelValues(string(obs.Operation)).Observe(obs.Seconds)
}

// ObserveHTTPRequest records auth HTTP request count and duration.
func (r *AuthRegistry) ObserveHTTPRequest(obs HTTPRequestObservation) {
	r.httpRequestsTotal.WithLabelValues(obs.Route, obs.Method, obs.StatusCode).Inc()
	r.httpRequestDuration.WithLabelValues(obs.Route, obs.Method, obs.StatusCode).Observe(obs.Seconds)
}
