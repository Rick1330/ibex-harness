package http

import (
	"errors"
	"net/http"
	"time"

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

type authWriteCtx struct {
	w         http.ResponseWriter
	requestID string
	docsBase  string
}

// AuthMiddleware validates bearer tokens and attaches auth context.
func AuthMiddleware(validator auth.TokenValidator, log *logger.Logger, opts AuthOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			requestID, r := ensureAuthRequestID(r)
			awc := authWriteCtx{w: w, requestID: requestID, docsBase: ErrorDocsBaseFromContext(r.Context())}

			token, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
			if err != nil {
				writeAuthParseError(awc, err)
				return
			}

			res, err := validator.Validate(r.Context(), token)
			if err != nil {
				writeAuthValidateError(awc, r, log, err)
				return
			}
			if res.FromCache {
				w.Header().Set("X-IBEX-Auth-Cached", "true")
			}
			if !authorizeAuthResult(awc, res, opts) {
				return
			}

			ctx := auth.WithContext(r.Context(), res)
			ctx = WithAuthLatencyMs(ctx, clampUint16Ms(time.Since(start)))
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func ensureAuthRequestID(r *http.Request) (string, *http.Request) {
	requestID := RequestIDFromContext(r.Context())
	if requestID != "" {
		return requestID, r
	}
	requestID = reqid.New()
	return requestID, r.WithContext(WithRequestID(r.Context(), requestID))
}

func writeAuthParseError(awc authWriteCtx, err error) {
	if errors.Is(err, auth.ErrMissingToken) {
		apierror.WriteStatus(awc.w, http.StatusUnauthorized, apierror.CodeMissingToken,
			"Authorization header required", awc.requestID, apierror.WriteOpts{DocsBase: awc.docsBase})
		return
	}
	apierror.WriteStatus(awc.w, http.StatusUnauthorized, apierror.CodeInvalidToken,
		"Invalid Authorization header", awc.requestID,
		apierror.WriteOpts{Detail: err.Error(), DocsBase: awc.docsBase})
}

func writeAuthValidateError(awc authWriteCtx, r *http.Request, log *logger.Logger, err error) {
	switch {
	case errors.Is(err, auth.ErrInvalidToken):
		apierror.WriteStatus(awc.w, http.StatusUnauthorized, apierror.CodeInvalidToken,
			"Invalid or expired token", awc.requestID, apierror.WriteOpts{DocsBase: awc.docsBase})
	case errors.Is(err, auth.ErrAuthUnavailable):
		log.WarnCtx(r.Context(), "auth validate unavailable", "error", err)
		apierror.WriteStatus(awc.w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
			"Authentication service unavailable", awc.requestID, apierror.WriteOpts{DocsBase: awc.docsBase})
	default:
		log.ErrorCtx(r.Context(), "unexpected auth validation error", "error", err)
		apierror.WriteStatus(awc.w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
			"Authentication service unavailable", awc.requestID, apierror.WriteOpts{DocsBase: awc.docsBase})
	}
}

func authorizeAuthResult(awc authWriteCtx, res *auth.ValidateResult, opts AuthOptions) bool {
	if opts.PathOrgID != "" && res.OrgID != opts.PathOrgID {
		apierror.WriteStatus(awc.w, http.StatusForbidden, apierror.CodeInsufficientPermissions,
			"Insufficient permissions", awc.requestID,
			apierror.WriteOpts{Detail: "organization scope mismatch", DocsBase: awc.docsBase})
		return false
	}
	if opts.RequireProxyChatCompletion && !permissions.Has(res.Permissions, permissions.ProxyChatCompletion) {
		apierror.WriteStatus(awc.w, http.StatusForbidden, apierror.CodeInsufficientPermissions,
			"Insufficient permissions", awc.requestID,
			apierror.WriteOpts{Detail: "token lacks proxy chat completion permissions", DocsBase: awc.docsBase})
		return false
	}
	return true
}
