package http

import (
	"context"
	"errors"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"google.golang.org/protobuf/proto"
)

const policySnapshotUnavailableMessage = "The policy snapshot could not be verified. The request cannot be authorized."

// policySnapshotMetrics records issuance/verification outcomes.
type policySnapshotMetrics interface {
	IncPolicySnapshot(result string)
}

type policySnapshotHandler struct {
	fetcher  PolicySnapshotFetcher
	verifier *policysnapshot.Verifier
	class    policysnapshot.Class
	metrics  policySnapshotMetrics
	logger   *logger.Logger
	next     http.Handler
}

// PolicySnapshotMiddleware mints and verifies a signed policy snapshot for the
// verified principal before protected effects. Must run after
// AgentVerificationMiddleware and before RateLimitMiddleware: the selected
// agent is already validated, so issuance binds org/subject/agent/permissions
// for exactly this request.
func PolicySnapshotMiddleware(
	fetcher PolicySnapshotFetcher,
	verifier *policysnapshot.Verifier,
	class policysnapshot.Class,
	metrics policySnapshotMetrics,
	log *logger.Logger,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return &policySnapshotHandler{
			fetcher: fetcher, verifier: verifier, class: class,
			metrics: metrics, logger: log, next: next,
		}
	}
}

func (h *policySnapshotHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	requestID := RequestIDFromContext(r.Context())
	docsBase := ErrorDocsBaseFromContext(r.Context())

	authRes, agentRec, ok := policyRequestScope(w, r, requestID, docsBase)
	if !ok {
		return
	}
	if h.fetcher == nil || h.verifier == nil {
		h.writeUnavailable(w, r, requestID, docsBase, nil)
		return
	}
	claims, ok := h.mintAndVerify(w, r, authRes, agentRec, requestID, docsBase)
	if !ok {
		return
	}
	h.record(policysnapshot.MetricIssued)

	ctx := withVerifiedSnapshot(r.Context(), claims)
	h.next.ServeHTTP(w, r.WithContext(ctx))
}

// policyRequestScope loads the verified auth and agent context installed by
// earlier middleware, failing closed when either is absent.
func policyRequestScope(w http.ResponseWriter, r *http.Request, requestID, docsBase string) (*auth.ValidateResult, auth.AgentRecord, bool) {
	authRes, ok := auth.FromContext(r.Context())
	if !ok || authRes == nil {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestID,
			apierror.WriteOpts{Detail: "missing auth context", DocsBase: docsBase})
		return nil, auth.AgentRecord{}, false
	}
	agentRec, ok := AgentFromContext(r.Context())
	if !ok {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestID,
			apierror.WriteOpts{Detail: "missing agent context", DocsBase: docsBase})
		return nil, auth.AgentRecord{}, false
	}
	return authRes, agentRec, true
}

func (h *policySnapshotHandler) mintAndVerify(
	w http.ResponseWriter,
	r *http.Request,
	authRes *auth.ValidateResult,
	agentRec auth.AgentRecord,
	requestID, docsBase string,
) (policysnapshot.Claims, bool) {
	bearer, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
	if err != nil {
		h.record(policysnapshot.MetricInvalidToken)
		apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken,
			"Invalid Authorization header", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
		return policysnapshot.Claims{}, false
	}

	orgID := authRes.OrgID.String()
	agentID := agentRec.ID.String()
	envelope, err := h.fetcher.Issue(r.Context(), bearer, agentID)
	if err != nil {
		h.writeIssueError(w, r, err, requestID, docsBase, orgID, agentID)
		return policysnapshot.Claims{}, false
	}
	claims, err := h.verifier.Verify(policysnapshot.VerifyParams{
		Envelope:        *envelope,
		ExpectedOrgID:   orgID,
		ExpectedAgentID: agentID,
		Class:           h.class,
	})
	if err != nil {
		h.writeVerifyError(w, r, err, requestID, docsBase)
		return policysnapshot.Claims{}, false
	}
	return claims, true
}

// withVerifiedSnapshot stores verified claims and stamps the snapshot id and
// digest onto the additive principal context when present.
func withVerifiedSnapshot(ctx context.Context, claims policysnapshot.Claims) context.Context {
	ctx = WithPolicySnapshotClaims(ctx, claims)
	principal, ok := PrincipalContextFromContext(ctx)
	if !ok {
		return ctx
	}
	if enriched, ok := proto.Clone(principal).(*authv1.PrincipalContext); ok {
		enriched.AuthzSnapshotId = claims.SnapshotID
		enriched.AuthzSnapshotDigest = claims.Digest
		return WithPrincipalContext(ctx, enriched)
	}
	return ctx
}

func (h *policySnapshotHandler) writeIssueError(w http.ResponseWriter, r *http.Request, err error, requestID, docsBase, orgID, agentID string) {
	switch {
	case errors.Is(err, auth.ErrInvalidToken):
		h.record(policysnapshot.MetricInvalidToken)
		apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken,
			"Invalid Authorization header", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	case errors.Is(err, auth.ErrPolicySnapshotDenied):
		h.record(policysnapshot.MetricDenied)
		if h.logger != nil {
			h.logger.WarnCtx(r.Context(), "policy snapshot denied",
				"requesting_org_id", orgID,
				"target_resource_type", "agent",
				"target_resource_id", agentID,
				"request_id", requestID,
			)
		}
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeAgentNotAuthorized,
			"The agent is not authorized for this organization or is not active.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	default:
		h.writeUnavailable(w, r, requestID, docsBase, err)
	}
}

func (h *policySnapshotHandler) writeVerifyError(w http.ResponseWriter, r *http.Request, err error, requestID, docsBase string) {
	switch {
	case errors.Is(err, policysnapshot.ErrExpired):
		h.record(policysnapshot.MetricExpired)
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeSnapshotExpired,
			"The policy snapshot is outside its freshness window.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	case errors.Is(err, policysnapshot.ErrOrgMismatch):
		h.record(policysnapshot.MetricOrgMismatch)
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeSnapshotOrgMismatch,
			"The policy snapshot is not valid for this organization.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	case errors.Is(err, policysnapshot.ErrAgentMismatch):
		h.record(policysnapshot.MetricAgentMismatch)
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeSnapshotAgentMismatch,
			"The policy snapshot is not valid for this agent.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	case errors.Is(err, policysnapshot.ErrKeyUnknown):
		h.record(policysnapshot.MetricKeyUnknown)
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeSnapshotKeyUnknown,
			"The policy snapshot names an unknown signing key.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	case errors.Is(err, policysnapshot.ErrSignatureInvalid), errors.Is(err, policysnapshot.ErrMalformed):
		h.record(policysnapshot.MetricSignatureInvalid)
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeSnapshotSignatureInvalid,
			"The policy snapshot failed verification.", requestID,
			apierror.WriteOpts{DocsBase: docsBase})
	default:
		h.writeUnavailable(w, r, requestID, docsBase, err)
	}
}

func (h *policySnapshotHandler) writeUnavailable(w http.ResponseWriter, r *http.Request, requestID, docsBase string, err error) {
	h.record(policysnapshot.MetricUnavailable)
	if h.logger != nil {
		h.logger.WarnCtx(r.Context(), "policy snapshot unavailable", "error", err)
	}
	apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeSnapshotUnavailable,
		policySnapshotUnavailableMessage, requestID,
		apierror.WriteOpts{DocsBase: docsBase})
}

func (h *policySnapshotHandler) record(result string) {
	if h.metrics != nil {
		h.metrics.IncPolicySnapshot(result)
	}
}
