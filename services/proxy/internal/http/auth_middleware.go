package http

import (
	"context"
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

type requestIDKey struct{}

// AuthOptions configures auth middleware behavior per route.
type AuthOptions struct {
	RequireProxyChatCompletion bool
	PathOrgID                  string
}

// AuthMiddleware validates bearer tokens and attaches auth context.
func AuthMiddleware(validator auth.TokenValidator, meter *metrics.Metrics, logger *slog.Logger, opts AuthOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			requestID := uuid.NewString()
			ctx := context.WithValue(r.Context(), requestIDKey{}, requestID)

			start := time.Now()
			token, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
			if err != nil {
				result := "unauthenticated"
				if !errors.Is(err, auth.ErrMissingToken) {
					result = "error"
				}
				meter.ObserveAuthValidate(time.Since(start).Seconds(), result)
				if errors.Is(err, auth.ErrMissingToken) {
					proxyerrors.WriteJSON(w, http.StatusUnauthorized, proxyerrors.CodeMissingToken,
						"Authorization header required", "", requestID)
					return
				}
				proxyerrors.WriteJSON(w, http.StatusUnauthorized, proxyerrors.CodeInvalidToken,
					"Invalid Authorization header", err.Error(), requestID)
				return
			}

			res, err := validator.Validate(ctx, token)
			elapsed := time.Since(start).Seconds()
			if err != nil {
				switch {
				case errors.Is(err, auth.ErrInvalidToken):
					meter.ObserveAuthValidate(elapsed, "unauthenticated")
					proxyerrors.WriteJSON(w, http.StatusUnauthorized, proxyerrors.CodeInvalidToken,
						"Invalid or expired token", "", requestID)
					return
				case errors.Is(err, auth.ErrAuthUnavailable):
					meter.ObserveAuthValidate(elapsed, "error")
					logger.Warn("auth validate unavailable", "request_id", requestID)
					proxyerrors.WriteJSON(w, http.StatusServiceUnavailable, proxyerrors.CodeServiceDegraded,
						"Authentication service unavailable", "", requestID)
					return
				default:
					meter.ObserveAuthValidate(elapsed, "error")
					proxyerrors.WriteJSON(w, http.StatusServiceUnavailable, proxyerrors.CodeServiceDegraded,
						"Authentication service unavailable", "", requestID)
					return
				}
			}
			meter.ObserveAuthValidate(elapsed, "ok")

			if opts.PathOrgID != "" && res.OrgID != opts.PathOrgID {
				proxyerrors.WriteJSON(w, http.StatusForbidden, proxyerrors.CodeInsufficientPermissions,
					"Insufficient permissions", "organization scope mismatch", requestID)
				return
			}
			if opts.RequireProxyChatCompletion && !permissions.Has(res.Permissions, permissions.ProxyChatCompletion) {
				proxyerrors.WriteJSON(w, http.StatusForbidden, proxyerrors.CodeInsufficientPermissions,
					"Insufficient permissions", "token lacks proxy chat completion permissions", requestID)
				return
			}

			ctx = auth.WithContext(ctx, res)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func requestIDFromContext(ctx context.Context) string {
	if id, ok := ctx.Value(requestIDKey{}).(string); ok {
		return id
	}
	return ""
}
