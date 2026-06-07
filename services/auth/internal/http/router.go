package http

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	"github.com/Rick1330/ibex-harness/services/auth/internal/health"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"go.opentelemetry.io/otel/trace"
)

type response struct {
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

func NewRouter(cfg config.Config, log *logger.Logger, meter *metrics.Metrics, tracer trace.Tracer) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet) {
			return
		}
		writeJSON(w, http.StatusOK, response{Status: "ok"})
	})
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet) {
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 750*time.Millisecond)
		defer cancel()

		result := health.ReadyPostgres(ctx, cfg.PostgresDSN)
		if !result.OK {
			log.WarnCtx(r.Context(), "readiness check failed", "reason", result.Reason)
			writeJSON(w, http.StatusServiceUnavailable, response{Status: "not_ready", Reason: result.Reason})
			return
		}
		writeJSON(w, http.StatusOK, response{Status: "ok"})
	})
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet) {
			return
		}
		meter.ServeHTTP(w, r)
	})

	return meter.Middleware(telemetry.SpanMiddleware(tracer)(loggingMiddleware(log, mux)))
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
