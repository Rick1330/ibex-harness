package http

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"go.opentelemetry.io/otel/trace"
)

const msgInternalError = "Internal error"

type authProbeResponse struct {
	OrgID       string `json:"org_id"`
	Permissions int64  `json:"permissions"`
}

// RouterDeps wires the proxy HTTP handler and middleware chain.
type RouterDeps struct {
	Config             config.Config
	Logger             *logger.Logger
	Metrics            *metrics.ProxyRegistry
	Tracer             trace.Tracer
	Validator          auth.TokenValidator
	AgentVerifier      auth.AgentVerifier
	Limiter            ratelimit.Limiter
	DirectiveResolver  directive.Resolver
	SessionStore       session.Store
	SessionCache       *sessioncache.Cache
	CheckpointPool     *asyncpool.Pool
	GetOrCreateTimeout time.Duration
	Health             *healthcheck.Server
	ProviderRegistry   *provider.Registry
	TraceWriter        TraceWriter
	IdempotencyStore   idempotency.Store
}

// NewRouter builds the proxy HTTP handler. A non-nil error means the router
// was not fully initialized and must not be served.
func NewRouter(deps RouterDeps) (http.Handler, error) {
	deps.Config.ApplyDefaults()
	mux := http.NewServeMux()
	providerReg, err := resolveProviderRegistry(deps.ProviderRegistry)
	if err != nil {
		return nil, err
	}
	mountPublicRoutes(mux, deps)
	if deps.Validator != nil {
		prd := buildProtectedRouteDeps(deps, providerReg)
		prd.mux = mux
		registerProtectedRoutes(prd)
	}
	return wrapRouterHandler(deps, mux), nil
}

func resolveProviderRegistry(reg *provider.Registry) (*provider.Registry, error) {
	if reg != nil {
		return reg, nil
	}
	providerReg, err := provider.NewRegistry()
	if err != nil {
		return nil, fmt.Errorf("provider registry: %w", err)
	}
	return providerReg, nil
}

func mountPublicRoutes(mux *http.ServeMux, deps RouterDeps) {
	healthSrv := deps.Health
	if healthSrv == nil {
		healthSrv = &healthcheck.Server{}
	}
	mux.HandleFunc("/health", healthSrv.HealthHandler())
	mux.HandleFunc("/ready", readyWithLog(deps.Logger, healthSrv.ReadyHandler()))
	mux.Handle("/metrics", metrics.Handler(deps.Metrics.Gatherer()))
}

func buildProtectedRouteDeps(deps RouterDeps, providerReg *provider.Registry) protectedRouteDeps {
	return protectedRouteDeps{
		cfg:                      deps.Config,
		logger:                   deps.Logger,
		reg:                      deps.Metrics,
		validator:                deps.Validator,
		agentVerifier:            deps.AgentVerifier,
		limiter:                  deps.Limiter,
		directiveResolver:        deps.DirectiveResolver,
		sessionStore:             deps.SessionStore,
		sessionCache:             deps.SessionCache,
		checkpointPool:           deps.CheckpointPool,
		getOrCreateTimeout:       deps.GetOrCreateTimeout,
		docsBase:                 deps.Config.ErrorDocsBase,
		providerRegistry:         providerReg,
		traceWriter:              httptrace.EffectiveWriter(deps.TraceWriter),
		idempotencyStore:         deps.IdempotencyStore,
		idempotencyTimeout:       deps.Config.IdempotencyRedisTimeout,
		idempotencyCommitTimeout: idempotencyCASHTimeout(deps.Config.IdempotencyRedisTimeout),
	}
}

func wrapRouterHandler(deps RouterDeps, mux *http.ServeMux) http.Handler {
	return RequestContextMiddleware(deps.Config)(
		telemetry.SpanMiddleware(deps.Tracer)(
			metrics.HTTPMiddleware(deps.Metrics)(
				ResponseHeadersMiddleware(deps.Config)(
					loggingMiddleware(deps.Logger, mux),
				),
			),
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
			msgInternalError, requestIDFromContext(r.Context()),
			apierror.WriteOpts{Detail: "missing auth context", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(authProbeResponse{
		OrgID:       res.OrgID.String(),
		Permissions: res.Permissions,
	})
}

func handleChatCompletions(w http.ResponseWriter, r *http.Request, h chatCompletionHandler) {
	h.serve(w, r)
}

type chatCompletionHandler struct {
	log                      *logger.Logger
	docsBase                 string
	metrics                  *metrics.ProxyRegistry
	sessionStore             session.Store
	sessionCache             *sessioncache.Cache
	checkpointPool           *asyncpool.Pool
	getOrCreateTimeout       time.Duration
	traceWriter              TraceWriter
	idempotencyStore         idempotency.Store
	idempotencyTimeout       time.Duration
	idempotencyCommitTimeout time.Duration
}

func (h chatCompletionHandler) serve(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost, h.docsBase) {
		return
	}
	parsed, ok := llm.ChatRequestFromContext(r.Context())
	if !ok {
		requestID := requestIDFromContext(r.Context())
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "chat request not parsed", DocsBase: h.docsBase})
		return
	}
	prov, ok := provider.ProviderFromContext(r.Context())
	if !ok {
		requestID := requestIDFromContext(r.Context())
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "provider not selected", DocsBase: h.docsBase})
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

// Flush implements http.Flusher for SSE streaming through middleware wrappers.
func (r *statusRecorder) Flush() {
	flushIfSupported(r.ResponseWriter)
}

func (r *statusRecorder) Unwrap() http.ResponseWriter {
	return r.ResponseWriter
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
