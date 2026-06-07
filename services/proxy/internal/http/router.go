package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/health"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"go.opentelemetry.io/otel/trace"
)

type response struct {
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

type authProbeResponse struct {
	OrgID       string `json:"org_id"`
	Permissions int64  `json:"permissions"`
}

// RouterDeps wires the proxy HTTP handler and middleware chain.
type RouterDeps struct {
	Config        config.Config
	Logger        *logger.Logger
	Metrics       *metrics.Metrics
	Tracer        trace.Tracer
	Validator     auth.TokenValidator
	AgentVerifier auth.AgentVerifier
	Limiter       ratelimit.Limiter
}

// NewRouter builds the proxy HTTP handler with optional auth validator for protected routes.
func NewRouter(deps RouterDeps) http.Handler {
	cfg := deps.Config
	logger := deps.Logger
	meter := deps.Metrics
	validator := deps.Validator
	agentVerifier := deps.AgentVerifier
	limiter := deps.Limiter
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
			logger.WarnCtx(r.Context(), "readiness check failed", "reason", result.Reason)
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
		registerProtectedRoutes(protectedRouteDeps{
			mux:           mux,
			cfg:           cfg,
			logger:        logger,
			meter:         meter,
			validator:     validator,
			agentVerifier: agentVerifier,
			limiter:       limiter,
			docsBase:      docsBase,
		})
	}

	handler := meter.Middleware(
		RequestContextMiddleware(cfg)(
			telemetry.SpanMiddleware(deps.Tracer)(
				ResponseHeadersMiddleware(cfg)(
					loggingMiddleware(logger, mux),
				),
			),
		),
	)
	return handler
}

func chain(middlewares ...func(http.Handler) http.Handler) func(http.Handler) http.Handler {
	return func(final http.Handler) http.Handler {
		h := final
		for i := len(middlewares) - 1; i >= 0; i-- {
			if middlewares[i] == nil {
				continue
			}
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

func handleChatCompletions(w http.ResponseWriter, r *http.Request, log *logger.Logger, docsBase string) {
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
		log.InfoCtx(ctx, "chat completion parsed",
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
