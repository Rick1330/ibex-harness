package auth

import (
	"context"
	"errors"
	"strings"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

const authInactiveAgentMessage = "agent is not active"

var (
	// ErrAgentNotAuthorized indicates the agent does not exist or belongs to another org.
	ErrAgentNotAuthorized = errors.New("agent not authorized")
	// ErrAgentSuspended indicates the agent exists but is not active.
	ErrAgentSuspended = errors.New("agent suspended")
	// ErrAgentVerifyUnavailable indicates ValidateAgent could not be reached or timed out.
	ErrAgentVerifyUnavailable = errors.New("agent verify unavailable")
)

// AgentRecord holds verified agent fields from ValidateAgent.
type AgentRecord struct {
	ID     uuid.UUID
	OrgID  uuid.UUID
	Status string
}

// AgentVerifier validates agent ownership for the authenticated org.
type AgentVerifier interface {
	Verify(ctx context.Context, bearer, agentID, orgID string) (*AgentRecord, error)
}

// GRPCAgentVerifier calls AuthService.ValidateAgent with bearer metadata.
type GRPCAgentVerifier struct {
	client  authv1.AuthServiceClient
	timeout time.Duration
}

// NewGRPCAgentVerifier creates an agent verifier using the given client and per-call timeout.
func NewGRPCAgentVerifier(client authv1.AuthServiceClient, timeout time.Duration) *GRPCAgentVerifier {
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &GRPCAgentVerifier{client: client, timeout: timeout}
}

// Verify calls auth ValidateAgent with a bounded deadline and forwarded bearer token.
func (v *GRPCAgentVerifier) Verify(ctx context.Context, bearer, agentID, orgID string) (*AgentRecord, error) {
	callCtx, cancel := context.WithTimeout(ctx, v.timeout)
	defer cancel()

	md := metadata.Pairs("authorization", "Bearer "+bearer)
	callCtx = metadata.NewOutgoingContext(callCtx, md)

	resp, err := v.client.ValidateAgent(callCtx, &authv1.ValidateAgentRequest{
		AgentId: agentID,
		OrgId:   orgID,
	})
	if err != nil {
		return nil, mapValidateAgentError(err, callCtx)
	}

	id, err := uuid.Parse(resp.GetAgentId())
	if err != nil {
		return nil, ErrAgentVerifyUnavailable
	}
	oid, err := uuid.Parse(resp.GetOrgId())
	if err != nil {
		return nil, ErrAgentVerifyUnavailable
	}

	return &AgentRecord{
		ID:     id,
		OrgID:  oid,
		Status: resp.GetStatus(),
	}, nil
}

func mapValidateAgentError(err error, callCtx context.Context) error {
	if st, ok := status.FromError(err); ok {
		if mapped := mapGRPCAgentStatus(st.Code(), st.Message()); mapped != nil {
			return mapped
		}
	}
	if isAgentVerifyTimeout(callCtx, err) {
		return ErrAgentVerifyUnavailable
	}
	return ErrAgentVerifyUnavailable
}

func mapGRPCAgentStatus(code codes.Code, msg string) error {
	switch code {
	case codes.PermissionDenied:
		if strings.Contains(msg, authInactiveAgentMessage) {
			return ErrAgentSuspended
		}
		return ErrAgentNotAuthorized
	case codes.NotFound:
		return ErrAgentNotAuthorized
	case codes.Unauthenticated, codes.InvalidArgument:
		return ErrAgentNotAuthorized
	case codes.DeadlineExceeded, codes.Unavailable, codes.Canceled:
		return ErrAgentVerifyUnavailable
	default:
		return nil
	}
}

func isAgentVerifyTimeout(callCtx context.Context, err error) bool {
	return errors.Is(callCtx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded)
}
