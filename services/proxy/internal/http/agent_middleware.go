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
	verifier AgentVerifier
	logger   *logger.Logger
	next     http.Handler
}

// AgentVerificationMiddleware validates X-IBEX-Agent-ID against the authenticated org.
// Must run after AuthMiddleware and before RateLimitMiddleware.
func AgentVerificationMiddleware(
	verifier AgentVerifier,
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

	agentHeader, fe, ok := validatedAgentHeader(r.Header, requestID, docsBase)
	if !ok {
		writeAgentHeaderError(w, fe, requestID, docsBase)
		return
	}

	bearer, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
	if err != nil {
		apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken,
			"Invalid Authorization header", requestID,
			apierror.WriteOpts{Detail: err.Error(), DocsBase: docsBase})
		return
	}

	rec, err := h.verifier.Verify(r.Context(), bearer, agentHeader, authRes.OrgID.String())
	if err != nil {
		h.writeAgentVerifyError(w, err, agentVerifyErrorOpts{
			ctx: r.Context(), requestID: requestID, docsBase: docsBase,
			requestingOrg: authRes.OrgID.String(), agentID: agentHeader,
		})
		return
	}

	ctx := WithAgent(r.Context(), *rec)
	h.next.ServeHTTP(w, r.WithContext(ctx))
}

func validatedAgentHeader(h http.Header, requestID, docsBase string) (string, *apierror.FieldError, bool) {
	agentHeader := strings.TrimSpace(h.Get(validation.HeaderAgentID))
	if agentHeader == "" {
		return "", nil, false
	}
	if fe := validation.ValidateUUIDField("header."+validation.HeaderAgentID, agentHeader); fe != nil {
		return "", fe, false
	}
	return agentHeader, nil, true
}

func writeAgentHeaderError(w http.ResponseWriter, fe *apierror.FieldError, requestID, docsBase string) {
	if fe == nil {
		apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeMissingAgentID,
			"X-IBEX-Agent-ID header is required.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
		return
	}
	apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
		"Request validation failed.", requestID,
		apierror.WriteOpts{DocsBase: docsBase, FieldErrors: []apierror.FieldError{*fe}})
}

type agentVerifyErrorOpts struct {
	ctx           context.Context
	requestID     string
	docsBase      string
	requestingOrg string
	agentID       string
}

func (h *agentVerifyHandler) writeAgentVerifyError(w http.ResponseWriter, err error, opts agentVerifyErrorOpts) {
	switch {
	case errors.Is(err, auth.ErrAgentSuspended):
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeAgentSuspended,
			"The agent is not active for this organization.", opts.requestID,
			apierror.WriteOpts{DocsBase: opts.docsBase})
	case errors.Is(err, auth.ErrAgentNotAuthorized):
		h.auditAgentAuthorizationDenied(opts)
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

func (h *agentVerifyHandler) auditAgentAuthorizationDenied(opts agentVerifyErrorOpts) {
	if h.logger == nil {
		return
	}
	// Proxy cannot distinguish same-org miss from cross-org without leaking
	// existence; both map to ErrAgentNotAuthorized. Audit all denials for forensics.
	h.logger.WarnCtx(opts.ctx, "agent authorization denied",
		"requesting_org_id", opts.requestingOrg,
		"target_resource_type", "agent",
		"target_resource_id", opts.agentID,
		"request_id", opts.requestID,
	)
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
