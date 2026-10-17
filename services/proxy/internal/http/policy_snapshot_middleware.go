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

// policySnapshotRecorder records issuance/verification outcomes.
type policySnapshotRecorder interface {
	IncPolicySnapshot(result string)
}

type policySnapshotHandler struct {
	fetcher  PolicySnapshotFetcher
	verifier *policysnapshot.Verifier
	class    policysnapshot.Class
	metrics  policySnapshotRecorder
	logger   *logger.Logger
	next     http.Handler
}

// policySnapshotRequest carries per-request state through the middleware steps.
type policySnapshotRequest struct {
	w         http.ResponseWriter
	r         *http.Request
	requestID string
	docsBase  string
	auth      *auth.ValidateResult
	agent     auth.AgentRecord
}

// policySnapshotConfig configures one policy snapshot middleware stage.
type policySnapshotConfig struct {
	fetcher  PolicySnapshotFetcher
	verifier *policysnapshot.Verifier
	class    policysnapshot.Class
	metrics  policySnapshotRecorder
	logger   *logger.Logger
}

// PolicySnapshotMiddleware mints and verifies a signed policy snapshot for the
// verified principal before protected effects. Must run after
// AgentVerificationMiddleware and before RateLimitMiddleware: the selected
// agent is already validated, so issuance binds org/subject/agent/permissions
// for exactly this request.
func PolicySnapshotMiddleware(cfg policySnapshotConfig) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return &policySnapshotHandler{
			fetcher: cfg.fetcher, verifier: cfg.verifier, class: cfg.class,
			metrics: cfg.metrics, logger: cfg.logger, next: next,
		}
	}
}

func (h *policySnapshotHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	req := &policySnapshotRequest{
		w: w, r: r,
		requestID: RequestIDFromContext(r.Context()),
		docsBase:  ErrorDocsBaseFromContext(r.Context()),
	}
	if !req.loadScope() {
		return
	}
	if h.fetcher == nil || h.verifier == nil {
		h.writeUnavailable(req, nil)
		return
	}
	claims, ok := h.mintAndVerify(req)
	if !ok {
		return
	}
	h.record(policysnapshot.MetricIssued)

	ctx := withVerifiedSnapshot(req.r.Context(), claims)
	h.next.ServeHTTP(w, req.r.WithContext(ctx))
}

// failed writes a stable error envelope scoped to this request.
func (req *policySnapshotRequest) failed(status int, code apierror.Code, message, detail string) {
	apierror.WriteStatus(req.w, status, code, message, req.requestID,
		apierror.WriteOpts{Detail: detail, DocsBase: req.docsBase})
}

// loadScope loads the verified auth and agent context installed by earlier
// middleware, failing closed when either is absent.
func (req *policySnapshotRequest) loadScope() bool {
	authRes, ok := auth.FromContext(req.r.Context())
	if !ok || authRes == nil {
		req.failed(http.StatusInternalServerError, apierror.CodeServiceDegraded, "Internal error", "missing auth context")
		return false
	}
	agentRec, ok := AgentFromContext(req.r.Context())
	if !ok {
		req.failed(http.StatusInternalServerError, apierror.CodeServiceDegraded, "Internal error", "missing agent context")
		return false
	}
	req.auth = authRes
	req.agent = agentRec
	return true
}

func (h *policySnapshotHandler) mintAndVerify(req *policySnapshotRequest) (policysnapshot.Claims, bool) {
	bearer, err := auth.ParseAuthorizationHeader(req.r.Header.Get("Authorization"))
	if err != nil {
		h.record(policysnapshot.MetricInvalidToken)
		req.failed(http.StatusUnauthorized, apierror.CodeInvalidToken, "Invalid Authorization header", "")
		return policysnapshot.Claims{}, false
	}

	orgID := req.auth.OrgID.String()
	agentID := req.agent.ID.String()
	envelope, err := h.fetcher.Issue(req.r.Context(), bearer, agentID)
	if err != nil {
		h.writeIssueError(req, err, orgID, agentID)
		return policysnapshot.Claims{}, false
	}
	if envelope == nil {
		h.writeUnavailable(req, nil)
		return policysnapshot.Claims{}, false
	}
	claims, err := h.verifier.Verify(policysnapshot.VerifyParams{
		Envelope:        *envelope,
		ExpectedOrgID:   orgID,
		ExpectedAgentID: agentID,
		Class:           h.class,
	})
	if err != nil {
		h.writeVerifyError(req, err)
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

func (h *policySnapshotHandler) writeIssueError(req *policySnapshotRequest, err error, orgID, agentID string) {
	switch {
	case errors.Is(err, auth.ErrInvalidToken):
		h.record(policysnapshot.MetricInvalidToken)
		req.failed(http.StatusUnauthorized, apierror.CodeInvalidToken, "Invalid Authorization header", "")
	case errors.Is(err, auth.ErrPolicySnapshotDenied):
		h.record(policysnapshot.MetricDenied)
		if h.logger != nil {
			h.logger.WarnCtx(req.r.Context(), "policy snapshot denied",
				"requesting_org_id", orgID,
				"target_resource_type", "agent",
				"target_resource_id", agentID,
				"request_id", req.requestID,
			)
		}
		req.failed(http.StatusForbidden, apierror.CodeAgentNotAuthorized,
			"The agent is not authorized for this organization or is not active.", "")
	default:
		h.writeUnavailable(req, err)
	}
}

func (h *policySnapshotHandler) writeVerifyError(req *policySnapshotRequest, err error) {
	switch {
	case errors.Is(err, policysnapshot.ErrExpired):
		h.record(policysnapshot.MetricExpired)
		req.failed(http.StatusForbidden, apierror.CodeSnapshotExpired,
			"The policy snapshot is outside its freshness window.", "")
	case errors.Is(err, policysnapshot.ErrOrgMismatch):
		h.record(policysnapshot.MetricOrgMismatch)
		req.failed(http.StatusForbidden, apierror.CodeSnapshotOrgMismatch,
			"The policy snapshot is not valid for this organization.", "")
	case errors.Is(err, policysnapshot.ErrAgentMismatch):
		h.record(policysnapshot.MetricAgentMismatch)
		req.failed(http.StatusForbidden, apierror.CodeSnapshotAgentMismatch,
			"The policy snapshot is not valid for this agent.", "")
	case errors.Is(err, policysnapshot.ErrKeyUnknown):
		h.record(policysnapshot.MetricKeyUnknown)
		req.failed(http.StatusForbidden, apierror.CodeSnapshotKeyUnknown,
			"The policy snapshot names an unknown signing key.", "")
	case errors.Is(err, policysnapshot.ErrSignatureInvalid), errors.Is(err, policysnapshot.ErrMalformed):
		h.record(policysnapshot.MetricSignatureInvalid)
		req.failed(http.StatusForbidden, apierror.CodeSnapshotSignatureInvalid,
			"The policy snapshot failed verification.", "")
	default:
		h.writeUnavailable(req, err)
	}
}

func (h *policySnapshotHandler) writeUnavailable(req *policySnapshotRequest, err error) {
	h.record(policysnapshot.MetricUnavailable)
	if h.logger != nil {
		h.logger.WarnCtx(req.r.Context(), "policy snapshot unavailable", "error", err)
	}
	req.failed(http.StatusServiceUnavailable, apierror.CodeSnapshotUnavailable, policySnapshotUnavailableMessage, "")
}

func (h *policySnapshotHandler) record(result string) {
	if h.metrics != nil {
		h.metrics.IncPolicySnapshot(result)
	}
}
