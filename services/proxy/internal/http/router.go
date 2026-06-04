package http

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/health"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
)

type response struct {
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

type authProbeResponse struct {
	OrgID       string `json:"org_id"`
	Permissions int64  `json:"permissions"`
}

// NewRouter builds the proxy HTTP handler with optional auth validator for protected routes.
func NewRouter(cfg config.Config, logger *slog.Logger, meter *metrics.Metrics, validator auth.TokenValidator) http.Handler {
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

		result := health.ReadyRedis(ctx, cfg.RedisURL)
		if !result.OK {
			logger.Warn("readiness check failed", "reason", result.Reason)
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

	if validator != nil {
		authNone := AuthMiddleware(validator, meter, logger, AuthOptions{})
		mux.Handle("/v1/internal/auth-probe", authNone(http.HandlerFunc(handleAuthProbe)))

		authOrg := func(orgID string) func(http.Handler) http.Handler {
			return AuthMiddleware(validator, meter, logger, AuthOptions{PathOrgID: orgID})
		}
		mux.HandleFunc("/v1/orgs/{org_id}/auth-probe", func(w http.ResponseWriter, r *http.Request) {
			if !requireMethod(w, r, http.MethodGet) {
				return
			}
			orgID := strings.TrimSpace(r.PathValue("org_id"))
			authOrg(orgID)(http.HandlerFunc(handleAuthProbe)).ServeHTTP(w, r)
		})

		authChat := AuthMiddleware(validator, meter, logger, AuthOptions{RequireProxyChatCompletion: true})
		mux.Handle("/v1/chat/completions", authChat(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			handleChatCompletions(w, r, logger)
		})))
	}

	return meter.Middleware(loggingMiddleware(logger, mux))
}

func handleAuthProbe(w http.ResponseWriter, r *http.Request) {
	res, ok := auth.FromContext(r.Context())
	if !ok {
		proxyerrors.WriteJSON(w, http.StatusInternalServerError, proxyerrors.CodeServiceDegraded,
			"Internal error", "missing auth context", requestIDFromContext(r.Context()))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(authProbeResponse{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
	})
}

func handleChatCompletions(w http.ResponseWriter, r *http.Request, logger *slog.Logger) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	requestID := requestIDFromContext(r.Context())

	parsed, err := llm.ParseChatCompletionRequest(r.Body)
	if err != nil {
		proxyerrors.WriteJSON(w, http.StatusBadRequest, proxyerrors.CodeInvalidJSON,
			"Malformed JSON in request body", "", requestID)
		return
	}

	if res, ok := auth.FromContext(r.Context()); ok {
		logger.Info("chat completion parsed",
			"request_id", requestID,
			"org_id", res.OrgID,
			"model", parsed.Model,
			"message_count", len(parsed.Messages),
			"stream", parsed.Stream,
		)
	}
	_ = llm.WithChatRequest(r.Context(), parsed)

	proxyerrors.WriteJSON(w, http.StatusNotImplemented, proxyerrors.CodeProviderNotConfigured,
		"LLM provider not configured", "Phase 2 milestone required for upstream calls",
		requestID)
}

func loggingMiddleware(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)
		logger.Info("http request", "method", r.Method, "path", r.URL.Path, "status", rec.status, "duration_ms", time.Since(start).Milliseconds())
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
