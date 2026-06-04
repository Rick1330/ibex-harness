package http

import (
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
	"github.com/google/uuid"
)

// AuthOptions configures auth middleware behavior per route.
type AuthOptions struct {
	RequireProxyChatCompletion bool
	PathOrgID                  string
}

// AuthMiddleware validates bearer tokens and attaches auth context.
func AuthMiddleware(validator auth.TokenValidator, meter *metrics.Metrics, logger *slog.Logger, opts AuthOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			requestID := RequestIDFromContext(r.Context())
			if requestID == "" {
				requestID = uuid.NewString()
				r = r.WithContext(WithRequestID(r.Context(), requestID))
			}
			docsBase := ErrorDocsBaseFromContext(r.Context())
			ctx := r.Context()

			start := time.Now()
			token, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
			if err != nil {
				result := "unauthenticated"
				if !errors.Is(err, auth.ErrMissingToken) {
					result = "error"
				}
				meter.ObserveAuthValidate(time.Since(start).Seconds(), result)
				if errors.Is(err, auth.ErrMissingToken) {
					proxyerrors.Write(w, http.StatusUnauthorized, proxyerrors.CodeMissingToken,
						"Authorization header required", requestID, proxyerrors.WriteOpts{DocsBase: docsBase})
					return
				}
				proxyerrors.Write(w, http.StatusUnauthorized, proxyerrors.CodeInvalidToken,
					"Invalid Authorization header", requestID,
					proxyerrors.WriteOpts{Detail: err.Error(), DocsBase: docsBase})
				return
			}

			res, err := validator.Validate(ctx, token)
			elapsed := time.Since(start).Seconds()
			if err != nil {
				switch {
				case errors.Is(err, auth.ErrInvalidToken):
					meter.ObserveAuthValidate(elapsed, "unauthenticated")
					proxyerrors.Write(w, http.StatusUnauthorized, proxyerrors.CodeInvalidToken,
						"Invalid or expired token", requestID, proxyerrors.WriteOpts{DocsBase: docsBase})
					return
				case errors.Is(err, auth.ErrAuthUnavailable):
					meter.ObserveAuthValidate(elapsed, "error")
					logger.Warn("auth validate unavailable", "request_id", requestID)
					proxyerrors.Write(w, http.StatusServiceUnavailable, proxyerrors.CodeServiceDegraded,
						"Authentication service unavailable", requestID, proxyerrors.WriteOpts{DocsBase: docsBase})
					return
				default:
					meter.ObserveAuthValidate(elapsed, "error")
					proxyerrors.Write(w, http.StatusServiceUnavailable, proxyerrors.CodeServiceDegraded,
						"Authentication service unavailable", requestID, proxyerrors.WriteOpts{DocsBase: docsBase})
					return
				}
			}
			meter.ObserveAuthValidate(elapsed, "ok")

			if opts.PathOrgID != "" && res.OrgID != opts.PathOrgID {
				proxyerrors.Write(w, http.StatusForbidden, proxyerrors.CodeInsufficientPermissions,
					"Insufficient permissions", requestID,
					proxyerrors.WriteOpts{Detail: "organization scope mismatch", DocsBase: docsBase})
				return
			}
			if opts.RequireProxyChatCompletion && !permissions.Has(res.Permissions, permissions.ProxyChatCompletion) {
				proxyerrors.Write(w, http.StatusForbidden, proxyerrors.CodeInsufficientPermissions,
					"Insufficient permissions", requestID,
					proxyerrors.WriteOpts{Detail: "token lacks proxy chat completion permissions", DocsBase: docsBase})
				return
			}

			ctx = auth.WithContext(ctx, res)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
