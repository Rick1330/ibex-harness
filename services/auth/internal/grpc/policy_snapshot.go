package grpcserver

import (
	"context"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const errMsgPolicySnapshotUnavailable = "policy snapshot issuance unavailable"

// policySnapshotIssuerPort mints signed policy snapshots.
type policySnapshotIssuerPort interface {
	Issue(p policysnapshot.IssueParams) (policysnapshot.Envelope, error)
}

// IssuePolicySnapshot mints an immutable signed snapshot for the authenticated
// caller's org/subject/selected-agent scope. The envelope is verified by
// consumers against the AuthService policy-signing key set before any effect.
func (s *Server) IssuePolicySnapshot(
	ctx context.Context,
	req *authv1.IssuePolicySnapshotRequest,
) (*authv1.IssuePolicySnapshotResponse, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if strings.TrimSpace(caller.OrgID) == "" {
		return nil, status.Error(codes.Internal, "caller org unavailable")
	}
	agentID, err := policySnapshotAgentID(caller, req.GetAgentId())
	if err != nil {
		return nil, err
	}
	subjectID := strings.TrimSpace(caller.UserID)
	if subjectID == "" {
		subjectID = strings.TrimSpace(caller.TokenID)
	}
	if subjectID == "" {
		return nil, status.Error(codes.Internal, "caller subject unavailable")
	}
	if s.policyIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, errMsgPolicySnapshotUnavailable)
	}
	envelope, err := s.policyIssuer.Issue(policysnapshot.IssueParams{
		OrgID:       caller.OrgID,
		SubjectID:   subjectID,
		AgentID:     agentID,
		Permissions: caller.Permissions,
	})
	if err != nil {
		s.log.ErrorCtx(ctx, "policy snapshot issue failed", "error", err)
		return nil, status.Error(codes.Internal, "policy snapshot issue failed")
	}
	return &authv1.IssuePolicySnapshotResponse{Envelope: &authv1.PolicySnapshotEnvelope{
		Algorithm: envelope.Algorithm,
		KeyId:     envelope.KeyID,
		Payload:   envelope.Payload,
		Signature: envelope.Signature,
	}}, nil
}

// policySnapshotAgentID enforces that agent-scoped callers cannot widen their
// binding; org-scoped callers may select any agent and the proxy's prior
// ValidateAgent call establishes membership and active state in the same chain.
func policySnapshotAgentID(caller CallerContext, rawAgentID string) (string, error) {
	agentID := strings.TrimSpace(rawAgentID)
	if caller.AgentID != "" {
		if agentID == "" {
			return "", status.Error(codes.InvalidArgument, "agent_id is required for agent-scoped tokens")
		}
		if agentID != caller.AgentID {
			return "", status.Error(codes.PermissionDenied, errMsgForbidden)
		}
		return agentID, nil
	}
	if agentID == "" {
		return "", nil
	}
	if _, err := uuid.Parse(agentID); err != nil {
		return "", status.Error(codes.InvalidArgument, "invalid agent_id")
	}
	return agentID, nil
}
