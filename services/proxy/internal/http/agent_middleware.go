package http

import (
	"context"
	"errors"
	"net/http"
	"strings"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

type agentVerifyHandler struct {
	verifier auth.AgentVerifier
	logger   *logger.Logger
	next     http.Handler
}

// AgentVerificationMiddleware validates X-IBEX-Agent-ID against the authenticated org.
// Must run after AuthMiddleware and before RateLimitMiddleware.
func AgentVerificationMiddleware(
	verifier auth.AgentVerifier,
	log *logger.Logger,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return &agentVerifyHandler{
			verifier: verifier,
			logger:   log,
			next:     next,
		}
	}
}

func (h *agentVerifyHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	requestID := RequestIDFromContext(r.Context())
	docsBase := ErrorDocsBaseFromContext(r.Context())

	authRes, ok := auth.FromContext(r.Context())
	if !ok || authRes == nil {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestID,
			apierror.WriteOpts{Detail: "missing auth context", DocsBase: docsBase})
		return
	}

	agentHeader := strings.TrimSpace(r.Header.Get(validation.HeaderAgentID))
	if agentHeader == "" {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeMissingAgentID,
			"X-IBEX-Agent-ID header is required.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
		return
	}

	if fe := validation.ValidateUUIDField("header."+validation.HeaderAgentID, agentHeader); fe != nil {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
			"Request validation failed.", requestID,
			apierror.WriteOpts{DocsBase: docsBase, FieldErrors: []apierror.FieldError{*fe}})
		return
	}

	bearer, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
	if err != nil {
		apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken,
			"Invalid Authorization header", requestID,
			apierror.WriteOpts{Detail: err.Error(), DocsBase: docsBase})
		return
	}

	rec, err := h.verifier.Verify(r.Context(), bearer, agentHeader, authRes.OrgID)
	if err != nil {
		h.writeAgentVerifyError(w, err, agentVerifyErrorOpts{
			ctx:       r.Context(),
			requestID: requestID,
			docsBase:  docsBase,
		})
		return
	}

	ctx := WithAgent(r.Context(), *rec)
	h.next.ServeHTTP(w, r.WithContext(ctx))
}

type agentVerifyErrorOpts struct {
	ctx       context.Context
	requestID string
	docsBase  string
}

func (h *agentVerifyHandler) writeAgentVerifyError(w http.ResponseWriter, err error, opts agentVerifyErrorOpts) {
	switch {
	case errors.Is(err, auth.ErrAgentSuspended):
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeAgentSuspended,
			"The agent is not active for this organization.", opts.requestID,
			apierror.WriteOpts{DocsBase: opts.docsBase})
	case errors.Is(err, auth.ErrAgentNotAuthorized):
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeAgentNotAuthorized,
			"The agent is not authorized for this organization or is not active.", opts.requestID,
			apierror.WriteOpts{DocsBase: opts.docsBase})
	case errors.Is(err, auth.ErrAgentVerifyUnavailable):
		h.logger.WarnCtx(opts.ctx, "agent verify unavailable")
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeAuthUnavailable,
			"Authentication service unavailable. The request cannot be verified.", opts.requestID,
			apierror.WriteOpts{DocsBase: opts.docsBase})
	default:
		h.logger.WarnCtx(opts.ctx, "agent verify failed", "error", err)
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeAuthUnavailable,
			"Authentication service unavailable. The request cannot be verified.", opts.requestID,
			apierror.WriteOpts{DocsBase: opts.docsBase})
	}
}

// parseAgentIDHeader parses X-IBEX-Agent-ID when present (used by rate limit scope).
func parseAgentIDHeader(h http.Header) uuid.UUID {
	raw := strings.TrimSpace(h.Get(validation.HeaderAgentID))
	if raw == "" {
		return uuid.Nil
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		return uuid.Nil
	}
	return id
}
