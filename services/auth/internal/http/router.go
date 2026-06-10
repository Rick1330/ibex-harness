package http

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"go.opentelemetry.io/otel/trace"
)

type response struct {
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

// NewRouter builds the auth HTTP handler including health, ready, and metrics routes.
func NewRouter(log *logger.Logger, reg *metrics.AuthRegistry, tracer trace.Tracer, healthSrv *healthcheck.Server) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthSrv.HealthHandler())
	mux.HandleFunc("/ready", readyWithLog(log, healthSrv.ReadyHandler()))
	mux.Handle("/metrics", metrics.Handler(reg.Gatherer()))

	return telemetry.SpanMiddleware(tracer)(
		metrics.AuthHTTPMiddleware(reg)(
			loggingMiddleware(log, mux),
		),
	)
}

func readyWithLog(log *logger.Logger, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next(rec, r)
		if rec.status == http.StatusServiceUnavailable {
			log.WarnCtx(r.Context(), "readiness check failed")
		}
	}
}

func loggingMiddleware(log *logger.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		log.DebugCtx(r.Context(), "http request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", rec.status,
			"duration_ms", time.Since(start).Milliseconds(),
		)
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func writeJSON(w http.ResponseWriter, status int, body response) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func requireMethod(w http.ResponseWriter, r *http.Request, method string) bool {
	if r.Method == method {
		return true
	}
	w.Header().Set("Allow", method)
	writeJSON(w, http.StatusMethodNotAllowed, response{Status: "error", Reason: "method not allowed"})
	return false
}
