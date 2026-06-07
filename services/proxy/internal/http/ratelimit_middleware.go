package http

import (
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/google/uuid"
)

type rateLimitResponseWriter struct {
	http.ResponseWriter
	limit     int
	remaining int
	resetUnix int64
	wrote     bool
}

func (w *rateLimitResponseWriter) WriteHeader(status int) {
	w.ensureHeaders()
	w.ResponseWriter.WriteHeader(status)
}

func (w *rateLimitResponseWriter) Write(b []byte) (int, error) {
	w.ensureHeaders()
	return w.ResponseWriter.Write(b)
}

func (w *rateLimitResponseWriter) ensureHeaders() {
	if w.wrote {
		return
	}
	w.wrote = true
	setRateLimitHeaders(w.ResponseWriter, w.limit, w.remaining, w.resetUnix)
}

type rateLimitHandler struct {
	limiter ratelimit.Limiter
	logger  *logger.Logger
	next    http.Handler
}

// RateLimitMiddleware enforces org-level rate limits after authentication.
// On Redis failure: fail open (allow request) with warning log.
func RateLimitMiddleware(limiter ratelimit.Limiter, log *logger.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return &rateLimitHandler{limiter: limiter, logger: log, next: next}
	}
}

func (h *rateLimitHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFromContext(r.Context())
	docsBase := ErrorDocsBaseFromContext(r.Context())

	orgUUID, agentUUID, ok := rateLimitScopeFromRequest(r)
	if !ok {
		writeRateLimitInternalError(w, requestID, docsBase, "missing auth context")
		return
	}
	if orgUUID == uuid.Nil {
		writeRateLimitInternalError(w, requestID, docsBase, "invalid org_id in auth context")
		return
	}

	res, _ := auth.FromContext(r.Context())
	result, err := h.limiter.Check(r.Context(), orgUUID, agentUUID)
	if err != nil {
		h.logger.WarnCtx(r.Context(), "rate limit check failed; failing open",
			"org_id", res.OrgID,
			"error", err,
		)
		h.next.ServeHTTP(w, r)
		return
	}
	if !result.Allowed {
		writeRateLimitExceeded(w, requestID, docsBase, result)
		return
	}

	wrapped := &rateLimitResponseWriter{
		ResponseWriter: w,
		limit:          result.Limit,
		remaining:      result.Remaining,
		resetUnix:      result.ResetUnix,
	}
	h.next.ServeHTTP(wrapped, r)
}

func rateLimitScopeFromRequest(r *http.Request) (orgUUID, agentUUID uuid.UUID, ok bool) {
	res, ok := auth.FromContext(r.Context())
	if !ok {
		return uuid.Nil, uuid.Nil, false
	}
	orgUUID, err := uuid.Parse(res.OrgID)
	if err != nil {
		return uuid.Nil, uuid.Nil, true
	}
	if rec, ok := AgentFromContext(r.Context()); ok {
		return orgUUID, rec.ID, true
	}
	return orgUUID, parseAgentIDHeader(r.Header), true
}

func writeRateLimitInternalError(w http.ResponseWriter, requestID, docsBase, detail string) {
	proxyerrors.Write(w, http.StatusInternalServerError, proxyerrors.CodeServiceDegraded,
		"Internal error", requestID,
		proxyerrors.WriteOpts{Detail: detail, DocsBase: docsBase})
}

func writeRateLimitExceeded(w http.ResponseWriter, requestID, docsBase string, result ratelimit.Result) {
	w.Header().Set("Retry-After", strconv.Itoa(retryAfterSeconds(result.RetryAfter)))
	setRateLimitHeaders(w, result.Limit, 0, result.ResetUnix)
	proxyerrors.Write(w, http.StatusTooManyRequests, proxyerrors.CodeRateLimited,
		"Rate limit exceeded for this organization", requestID,
		proxyerrors.WriteOpts{
			Detail:   "You have exceeded the request rate limit. Please retry after the indicated time.",
			DocsBase: docsBase,
		})
}

func setRateLimitHeaders(w http.ResponseWriter, limit, remaining int, resetUnix int64) {
	w.Header().Set("X-RateLimit-Limit", strconv.Itoa(limit))
	w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remaining))
	w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(resetUnix, 10))
}

func retryAfterSeconds(d time.Duration) int {
	if d <= 0 {
		return 1
	}
	sec := int(math.Ceil(d.Seconds()))
	if sec < 1 {
		return 1
	}
	return sec
}
