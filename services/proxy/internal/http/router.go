package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"go.opentelemetry.io/otel/trace"
)

type authProbeResponse struct {
	OrgID       string `json:"org_id"`
	Permissions int64  `json:"permissions"`
}

// RouterDeps wires the proxy HTTP handler and middleware chain.
type RouterDeps struct {
	Config           config.Config
	Logger           *logger.Logger
	Metrics          *metrics.ProxyRegistry
	Tracer           trace.Tracer
	Validator        auth.TokenValidator
	AgentVerifier    auth.AgentVerifier
	Limiter          ratelimit.Limiter
	Health           *healthcheck.Server
	ProviderRegistry *provider.Registry
}

// NewRouter builds the proxy HTTP handler with optional auth validator for protected routes.
func NewRouter(deps RouterDeps) http.Handler {
	cfg := deps.Config
	logger := deps.Logger
	reg := deps.Metrics
	validator := deps.Validator
	agentVerifier := deps.AgentVerifier
	limiter := deps.Limiter
	cfg.ApplyDefaults()
	mux := http.NewServeMux()
	docsBase := cfg.ErrorDocsBase
	providerReg := deps.ProviderRegistry
	if providerReg == nil {
		var regErr error
		providerReg, regErr = provider.NewRegistry()
		if regErr != nil {
			panic("provider registry: " + regErr.Error())
		}
	}

	healthSrv := deps.Health
	if healthSrv == nil {
		healthSrv = &healthcheck.Server{}
	}
	mux.HandleFunc("/health", healthSrv.HealthHandler())
	mux.HandleFunc("/ready", readyWithLog(logger, healthSrv.ReadyHandler()))
	mux.Handle("/metrics", metrics.Handler(reg.Gatherer()))

	if validator != nil {
		registerProtectedRoutes(protectedRouteDeps{
			mux:              mux,
			cfg:              cfg,
			logger:           logger,
			reg:              reg,
			validator:        validator,
			agentVerifier:    agentVerifier,
			limiter:          limiter,
			docsBase:         docsBase,
			providerRegistry: providerReg,
		})
	}

	handler := RequestContextMiddleware(cfg)(
		telemetry.SpanMiddleware(deps.Tracer)(
			metrics.HTTPMiddleware(reg)(
				ResponseHeadersMiddleware(cfg)(
					loggingMiddleware(logger, mux),
				),
			),
		),
	)
	return handler
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
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestIDFromContext(r.Context()),
			apierror.WriteOpts{Detail: "missing auth context", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(authProbeResponse{
		OrgID:       res.OrgID,
		Permissions: res.Permissions,
	})
}

func handleChatCompletions(w http.ResponseWriter, r *http.Request, h chatCompletionHandler) {
	h.serve(w, r)
}

type chatCompletionHandler struct {
	log         *logger.Logger
	docsBase    string
	providerReg *provider.Registry
}

func (h chatCompletionHandler) serve(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost, h.docsBase) {
		return
	}
	requestID := requestIDFromContext(r.Context())

	parsed, ok := parseAndValidateChatRequest(w, r, requestID, h.docsBase)
	if !ok {
		return
	}

	ctx := llm.WithChatRequest(r.Context(), parsed)

	if res, ok := auth.FromContext(ctx); ok {
		h.log.InfoCtx(ctx, "chat completion parsed",
			"org_id", res.OrgID,
			"model", parsed.Model,
			"message_count", len(parsed.Messages),
			"stream", parsed.Stream,
		)
	}

	if parsed.Stream {
		writeStreamingNotSupported(w, requestID, h.docsBase)
		return
	}

	prov, err := h.providerReg.For(parsed.Model)
	if err != nil {
		if errors.Is(err, provider.ErrNoProviderForModel) {
			writeProviderNotConfigured(w, requestID, h.docsBase, "No provider registered for model "+parsed.Model)
			return
		}
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestID,
			apierror.WriteOpts{Detail: "provider registry lookup failed", DocsBase: h.docsBase})
		return
	}

	h.forwardChatCompletion(chatForwardParams{
		w: w, r: r, parsed: parsed, prov: prov,
	})
}

// parseAndValidateChatRequest parses and validates the chat body.
// Returns (parsed, true) on success; on failure it writes the appropriate error response and returns (_, false).
func parseAndValidateChatRequest(w http.ResponseWriter, r *http.Request, requestID, docsBase string) (*llm.ChatCompletionRequest, bool) {
	if fieldErrors := validation.ValidateChatHeaders(r.Header); len(fieldErrors) > 0 {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed", requestID, apierror.WriteOpts{DocsBase: docsBase, FieldErrors: fieldErrors})
		return nil, false
	}

	parsed, err := llm.ParseChatCompletionRequest(r.Body)
	if err != nil {
		writeChatParseError(w, requestID, docsBase, err)
		return nil, false
	}

	if fieldErrors := validation.ValidateChatCompletionRequest(parsed); len(fieldErrors) > 0 {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed", requestID, apierror.WriteOpts{DocsBase: docsBase, FieldErrors: fieldErrors})
		return nil, false
	}

	return parsed, true
}

func writeChatParseError(w http.ResponseWriter, requestID, docsBase string, err error) {
	opts := apierror.WriteOpts{DocsBase: docsBase}
	if IsMaxBytesError(err) {
		apierror.WriteStatus(w, http.StatusRequestEntityTooLarge, apierror.CodePayloadTooLarge,
			"Request body too large", requestID, opts)
		return
	}
	var maxErr *http.MaxBytesError
	if errors.As(err, &maxErr) {
		apierror.WriteStatus(w, http.StatusRequestEntityTooLarge, apierror.CodePayloadTooLarge,
			"Request body too large", requestID, opts)
		return
	}
	apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeInvalidJSON,
		"Malformed JSON in request body", requestID, opts)
}

func writeProviderNotConfigured(w http.ResponseWriter, requestID, docsBase, detail string) {
	apierror.WriteStatus(w, http.StatusNotImplemented, apierror.CodeProviderNotConfigured,
		"LLM provider not configured", requestID,
		apierror.WriteOpts{Detail: detail, DocsBase: docsBase})
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

func requireMethod(w http.ResponseWriter, r *http.Request, method, docsBase string) bool {
	if r.Method == method {
		return true
	}
	w.Header().Set("Allow", method)
	apierror.WriteStatus(w, http.StatusMethodNotAllowed, apierror.CodeMethodNotAllowed,
		"Method not allowed", requestIDFromContext(r.Context()),
		apierror.WriteOpts{Detail: "expected " + method, DocsBase: docsBase})
	return false
}
