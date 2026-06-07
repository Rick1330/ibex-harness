package http

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

type agentVerifyHandler struct {
	verifier auth.AgentVerifier
	meter    *metrics.Metrics
	logger   *logger.Logger
	next     http.Handler
}

// AgentVerificationMiddleware validates X-IBEX-Agent-ID against the authenticated org.
// Must run after AuthMiddleware and before RateLimitMiddleware.
func AgentVerificationMiddleware(
	verifier auth.AgentVerifier,
	meter *metrics.Metrics,
	log *logger.Logger,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return &agentVerifyHandler{
			verifier: verifier,
			meter:    meter,
			logger:   log,
			next:     next,
		}
	}
}

func (h *agentVerifyHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	requestID := RequestIDFromContext(r.Context())
	docsBase := ErrorDocsBaseFromContext(r.Context())
	start := time.Now()

	authRes, ok := auth.FromContext(r.Context())
	if !ok || authRes == nil {
		h.meter.ObserveAgentValidate(time.Since(start).Seconds(), "error")
		http.Error(w, "internal server error", http.StatusInternalServerError)
		return
	}

	agentHeader := strings.TrimSpace(r.Header.Get(validation.HeaderAgentID))
	if agentHeader == "" {
		h.meter.ObserveAgentValidate(time.Since(start).Seconds(), "missing")
		proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeMissingAgentID,
			"X-IBEX-Agent-ID header is required.", requestID,
			proxyerrors.WriteOpts{DocsBase: docsBase})
		return
	}

	if fe := validation.ValidateUUIDField("header."+validation.HeaderAgentID, agentHeader); fe != nil {
		h.meter.ObserveAgentValidate(time.Since(start).Seconds(), "invalid")
		proxyerrors.Write(w, http.StatusBadRequest, proxyerrors.CodeValidationError,
			"Request validation failed.", requestID,
			proxyerrors.WriteOpts{DocsBase: docsBase, FieldErrors: []proxyerrors.FieldError{*fe}})
		return
	}

	bearer, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
	if err != nil {
		h.meter.ObserveAgentValidate(time.Since(start).Seconds(), "error")
		proxyerrors.Write(w, http.StatusUnauthorized, proxyerrors.CodeInvalidToken,
			"Invalid Authorization header", requestID,
			proxyerrors.WriteOpts{Detail: err.Error(), DocsBase: docsBase})
		return
	}

	rec, err := h.verifier.Verify(r.Context(), bearer, agentHeader, authRes.OrgID)
	elapsed := time.Since(start).Seconds()
	if err != nil {
		h.writeAgentVerifyError(w, err, agentVerifyErrorOpts{
			ctx:       r.Context(),
			requestID: requestID,
			docsBase:  docsBase,
			elapsed:   elapsed,
		})
		return
	}

	h.meter.ObserveAgentValidate(elapsed, "ok")
	ctx := WithAgent(r.Context(), *rec)
	h.next.ServeHTTP(w, r.WithContext(ctx))
}

type agentVerifyErrorOpts struct {
	ctx       context.Context
	requestID string
	docsBase  string
	elapsed   float64
}

func (h *agentVerifyHandler) writeAgentVerifyError(w http.ResponseWriter, err error, opts agentVerifyErrorOpts) {
	switch {
	case errors.Is(err, auth.ErrAgentSuspended):
		h.meter.ObserveAgentValidate(opts.elapsed, "suspended")
		proxyerrors.Write(w, http.StatusForbidden, proxyerrors.CodeAgentSuspended,
			"The agent is not active for this organization.", opts.requestID,
			proxyerrors.WriteOpts{DocsBase: opts.docsBase})
	case errors.Is(err, auth.ErrAgentNotAuthorized):
		h.meter.ObserveAgentValidate(opts.elapsed, "forbidden")
		proxyerrors.Write(w, http.StatusForbidden, proxyerrors.CodeAgentNotAuthorized,
			"The agent is not authorized for this organization or is not active.", opts.requestID,
			proxyerrors.WriteOpts{DocsBase: opts.docsBase})
	case errors.Is(err, auth.ErrAgentVerifyUnavailable):
		h.meter.ObserveAgentValidate(opts.elapsed, "error")
		h.logger.WarnCtx(opts.ctx, "agent verify unavailable")
		proxyerrors.Write(w, http.StatusServiceUnavailable, proxyerrors.CodeAuthUnavailable,
			"Authentication service unavailable. The request cannot be verified.", opts.requestID,
			proxyerrors.WriteOpts{DocsBase: opts.docsBase})
	default:
		h.meter.ObserveAgentValidate(opts.elapsed, "error")
		h.logger.WarnCtx(opts.ctx, "agent verify failed", "error", err)
		proxyerrors.Write(w, http.StatusServiceUnavailable, proxyerrors.CodeAuthUnavailable,
			"Authentication service unavailable. The request cannot be verified.", opts.requestID,
			proxyerrors.WriteOpts{DocsBase: opts.docsBase})
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
