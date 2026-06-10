package http

import (
	"errors"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
)

// AuthOptions configures auth middleware behavior per route.
type AuthOptions struct {
	RequireProxyChatCompletion bool
	PathOrgID                  string
}

// AuthMiddleware validates bearer tokens and attaches auth context.
func AuthMiddleware(validator auth.TokenValidator, log *logger.Logger, opts AuthOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			requestID := RequestIDFromContext(r.Context())
			if requestID == "" {
				requestID = reqid.New()
				r = r.WithContext(WithRequestID(r.Context(), requestID))
			}
			docsBase := ErrorDocsBaseFromContext(r.Context())
			ctx := r.Context()

			token, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
			if err != nil {
				if errors.Is(err, auth.ErrMissingToken) {
					apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeMissingToken,
						"Authorization header required", requestID, apierror.WriteOpts{DocsBase: docsBase})
					return
				}
				apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken,
					"Invalid Authorization header", requestID,
					apierror.WriteOpts{Detail: err.Error(), DocsBase: docsBase})
				return
			}

			res, err := validator.Validate(ctx, token)
			if err != nil {
				switch {
				case errors.Is(err, auth.ErrInvalidToken):
					apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken,
						"Invalid or expired token", requestID, apierror.WriteOpts{DocsBase: docsBase})
					return
				case errors.Is(err, auth.ErrAuthUnavailable):
					log.WarnCtx(r.Context(), "auth validate unavailable")
					apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
						"Authentication service unavailable", requestID, apierror.WriteOpts{DocsBase: docsBase})
					return
				default:
					log.ErrorCtx(r.Context(), "unexpected auth validation error", "error", err)
					apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
						"Authentication service unavailable", requestID, apierror.WriteOpts{DocsBase: docsBase})
					return
				}
			}

			if opts.PathOrgID != "" && res.OrgID != opts.PathOrgID {
				apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeInsufficientPermissions,
					"Insufficient permissions", requestID,
					apierror.WriteOpts{Detail: "organization scope mismatch", DocsBase: docsBase})
				return
			}
			if opts.RequireProxyChatCompletion && !permissions.Has(res.Permissions, permissions.ProxyChatCompletion) {
				apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeInsufficientPermissions,
					"Insufficient permissions", requestID,
					apierror.WriteOpts{Detail: "token lacks proxy chat completion permissions", DocsBase: docsBase})
				return
			}

			ctx = auth.WithContext(ctx, res)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
