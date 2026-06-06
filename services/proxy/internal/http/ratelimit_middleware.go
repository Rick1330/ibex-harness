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
	w.ResponseWriter.Header().Set("X-RateLimit-Limit", strconv.Itoa(w.limit))
	w.ResponseWriter.Header().Set("X-RateLimit-Remaining", strconv.Itoa(w.remaining))
	w.ResponseWriter.Header().Set("X-RateLimit-Reset", strconv.FormatInt(w.resetUnix, 10))
}

// RateLimitMiddleware enforces org-level rate limits after authentication.
// On Redis failure: fail open (allow request) with warning log.
func RateLimitMiddleware(limiter ratelimit.Limiter, logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			requestID := requestIDFromContext(r.Context())
			docsBase := ErrorDocsBaseFromContext(r.Context())

			res, ok := auth.FromContext(r.Context())
			if !ok {
				proxyerrors.Write(w, http.StatusInternalServerError, proxyerrors.CodeServiceDegraded,
					"Internal error", requestID,
					proxyerrors.WriteOpts{Detail: "missing auth context", DocsBase: docsBase})
				return
			}

			orgUUID, err := uuid.Parse(res.OrgID)
			if err != nil {
				proxyerrors.Write(w, http.StatusInternalServerError, proxyerrors.CodeServiceDegraded,
					"Internal error", requestID,
					proxyerrors.WriteOpts{Detail: "invalid org_id in auth context", DocsBase: docsBase})
				return
			}

			agentUUID := uuid.Nil
			if agentHeader := strings.TrimSpace(r.Header.Get(headerAgentID)); agentHeader != "" {
				if parsed, parseErr := uuid.Parse(agentHeader); parseErr == nil {
					agentUUID = parsed
				}
			}

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
				retrySec := retryAfterSeconds(result.RetryAfter)
				w.Header().Set("Retry-After", strconv.Itoa(retrySec))
				w.Header().Set("X-RateLimit-Limit", strconv.Itoa(result.Limit))
				w.Header().Set("X-RateLimit-Remaining", "0")
				w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(result.ResetUnix, 10))
				proxyerrors.Write(w, http.StatusTooManyRequests, proxyerrors.CodeRateLimited,
					"Rate limit exceeded for this organization", requestID,
					proxyerrors.WriteOpts{
						Detail:   "You have exceeded the request rate limit. Please retry after the indicated time.",
						DocsBase: docsBase,
					})
				return
			}

			wrapped := &rateLimitResponseWriter{
				ResponseWriter: w,
				limit:          result.Limit,
				remaining:      result.Remaining,
				resetUnix:      result.ResetUnix,
			}
			next.ServeHTTP(wrapped, r)
		})
	}
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
