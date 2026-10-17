package grpcserver

import (
	"context"
	"errors"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const errMsgPolicySnapshotUnavailable = "policy snapshot issuance unavailable"

// policySnapshotIssuer mints signed policy snapshots for the verified caller.
type policySnapshotIssuer interface {
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
	subjectID, err := policySnapshotSubject(caller)
	if err != nil {
		return nil, err
	}
	if s.policyIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, errMsgPolicySnapshotUnavailable)
	}
	if err := s.validateSnapshotAgent(ctx, caller.OrgID, agentID); err != nil {
		return nil, err
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

// policySnapshotSubject resolves the attested subject, preferring the user id
// and falling back to the token id.
func policySnapshotSubject(caller CallerContext) (string, error) {
	subjectID := strings.TrimSpace(caller.UserID)
	if subjectID == "" {
		subjectID = strings.TrimSpace(caller.TokenID)
	}
	if subjectID == "" {
		return "", status.Error(codes.Internal, "caller subject unavailable")
	}
	return subjectID, nil
}

// policySnapshotAgentID enforces that agent-scoped callers cannot widen their
// binding; org-scoped callers may select any agent, whose membership and active
// state are validated against the agent service before issuance.
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

// validateSnapshotAgent confirms the selected agent belongs to the caller's
// org and is active before any snapshot is minted for it.
func (s *Server) validateSnapshotAgent(ctx context.Context, orgID, agentID string) error {
	if agentID == "" {
		return nil
	}
	orgUUID, err := uuid.Parse(orgID)
	if err != nil {
		return status.Error(codes.Internal, "caller org unavailable")
	}
	agentUUID, err := uuid.Parse(agentID)
	if err != nil {
		return status.Error(codes.Internal, "caller agent binding invalid")
	}
	if _, err := s.agentService.ValidateForOrg(ctx, orgUUID, agentUUID); err != nil {
		return mapPolicySnapshotAgentErr(err)
	}
	return nil
}

func mapPolicySnapshotAgentErr(err error) error {
	switch {
	case errors.Is(err, service.ErrAgentNotAuthorized):
		return status.Error(codes.PermissionDenied, "agent not found")
	case errors.Is(err, service.ErrAgentInactive):
		return status.Error(codes.PermissionDenied, "agent is not active")
	case errors.Is(err, context.Canceled):
		return status.Error(codes.Canceled, "request canceled")
	case errors.Is(err, context.DeadlineExceeded):
		return status.Error(codes.DeadlineExceeded, "deadline exceeded")
	default:
		return status.Error(codes.Internal, "agent lookup failed")
	}
}
