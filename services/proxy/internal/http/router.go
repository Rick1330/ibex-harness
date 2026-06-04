package http

import (
	"context"
	"encoding/json"
	"errors"
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
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
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
	cfg.ApplyDefaults()
	mux := http.NewServeMux()
	docsBase := cfg.ErrorDocsBase

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet, docsBase) {
			return
		}
		writeJSON(w, http.StatusOK, response{Status: "ok"})
	})
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		if !requireMethod(w, r, http.MethodGet, docsBase) {
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
		if !requireMethod(w, r, http.MethodGet, docsBase) {
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
			if !requireMethod(w, r, http.MethodGet, docsBase) {
				return
			}
			orgID := strings.TrimSpace(r.PathValue("org_id"))
			chain(
				PathOrgUUIDMiddleware(docsBase),
				authOrg(orgID),
			)(http.HandlerFunc(handleAuthProbe)).ServeHTTP(w, r)
		})

		chatChain := chain(
			BodySizeLimitMiddleware(cfg.MaxRequestBodyBytes, docsBase),
			ContentTypeMiddleware(docsBase),
			AuthMiddleware(validator, meter, logger, AuthOptions{RequireProxyChatCompletion: true}),
		)
		mux.Handle("/v1/chat/completions", chatChain(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			handleChatCompletions(w, r, logger, docsBase)
		})))
	}

	handler := meter.Middleware(
		RequestContextMiddleware(cfg)(
			ResponseHeadersMiddleware(cfg)(
				loggingMiddleware(logger, mux),
			),
		),
	)
	return handler
}

func chain(middlewares ...func(http.Handler) http.Handler) func(http.Handler) http.Handler {
	return func(final http.Handler) http.Handler {
		h := final
		for i := len(middlewares) - 1; i >= 0; i-- {
			h = middlewares[i](h)
		}
		return h
	}
}

func handleAuthProbe(w http.ResponseWriter, r *http.Request) {
	res, ok := auth.FromContext(r.Context())
	if !ok {
		proxyerrors.Write(w, http.StatusInternalServerError, proxyerrors.CodeServiceDegraded,
			"Internal error", requestIDFromContext(r.Context()),
			proxyerrors.WriteOpts{Detail: "missing auth context", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(authProbeResponse{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
	})
}

func handleChatCompletions(w http.ResponseWriter, r *http.Request, logger *slog.Logger, docsBase string) {
	if !requireMethod(w, r, http.MethodPost, docsBase) {
		return
	}
	requestID := requestIDFromContext(r.Context())
	opts := proxyerrors.WriteOpts{DocsBase: docsBase}

	if fieldErrors := validation.ValidateChatHeaders(r.Header); len(fieldErrors) > 0 {
		proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeValidationError,
			"Request validation failed", requestID, proxyerrors.WriteOpts{DocsBase: docsBase, FieldErrors: fieldErrors})
		return
	}

	parsed, err := llm.ParseChatCompletionRequest(r.Body)
	if err != nil {
		if IsMaxBytesError(err) {
			proxyerrors.Write(w, http.StatusRequestEntityTooLarge, proxyerrors.CodePayloadTooLarge,
				"Request body too large", requestID, opts)
			return
		}
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			proxyerrors.Write(w, http.StatusRequestEntityTooLarge, proxyerrors.CodePayloadTooLarge,
				"Request body too large", requestID, opts)
			return
		}
		proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeInvalidJSON,
			"Malformed JSON in request body", requestID, opts)
		return
	}

	if fieldErrors := validation.ValidateChatCompletionRequest(parsed); len(fieldErrors) > 0 {
		proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeValidationError,
			"Request validation failed", requestID, proxyerrors.WriteOpts{DocsBase: docsBase, FieldErrors: fieldErrors})
		return
	}

	ctx := llm.WithChatRequest(r.Context(), parsed)

	if res, ok := auth.FromContext(ctx); ok {
		logger.Info("chat completion parsed",
			"request_id", requestID,
			"org_id", res.OrgID,
			"model", parsed.Model,
			"message_count", len(parsed.Messages),
			"stream", parsed.Stream,
		)
	}

	proxyerrors.Write(w, http.StatusNotImplemented, proxyerrors.CodeProviderNotConfigured,
		"LLM provider not configured", requestID,
		proxyerrors.WriteOpts{Detail: "Phase 2 milestone required for upstream calls", DocsBase: docsBase})
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

func requireMethod(w http.ResponseWriter, r *http.Request, method, docsBase string) bool {
	if r.Method == method {
		return true
	}
	w.Header().Set("Allow", method)
	proxyerrors.Write(w, http.StatusMethodNotAllowed, proxyerrors.CodeMethodNotAllowed,
		"Method not allowed", requestIDFromContext(r.Context()),
		proxyerrors.WriteOpts{Detail: "expected " + method, DocsBase: docsBase})
	return false
}
