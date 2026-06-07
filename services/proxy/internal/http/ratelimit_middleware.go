package http

import (
	"log/slog"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/google/uuid"
)

const headerAgentID = "X-IBEX-Agent-ID"

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

// RateLimitMiddleware enforces org-level rate limits after authentication.
// On Redis failure: fail open (allow request) with warning log.
func RateLimitMiddleware(limiter ratelimit.Limiter, logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			handleRateLimit(w, r, limiter, logger, next)
		})
	}
}

func handleRateLimit(w http.ResponseWriter, r *http.Request, limiter ratelimit.Limiter, logger *slog.Logger, next http.Handler) {
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
	result, err := limiter.Check(r.Context(), orgUUID, agentUUID)
	if err != nil {
		logger.Warn("rate limit check failed; failing open",
			"request_id", requestID,
			"org_id", res.OrgID,
			"error", err,
		)
		next.ServeHTTP(w, r)
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
	next.ServeHTTP(wrapped, r)
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
	agentUUID = parseOptionalAgentID(r.Header.Get(headerAgentID))
	return orgUUID, agentUUID, true
}

func parseOptionalAgentID(raw string) uuid.UUID {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return uuid.Nil
	}
	parsed, err := uuid.Parse(raw)
	if err != nil {
		return uuid.Nil
	}
	return parsed
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
