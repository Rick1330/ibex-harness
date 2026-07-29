package auth

import (
	"context"
	"fmt"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// GRPCValidator validates tokens via AuthService.ValidateToken.
type GRPCValidator struct {
	client  authv1.AuthServiceClient
	timeout time.Duration
}

// NewGRPCValidator creates a validator using the given client and per-call timeout.
func NewGRPCValidator(client authv1.AuthServiceClient, timeout time.Duration) (*GRPCValidator, error) {
	if isNilAuthClient(client) {
		return nil, fmt.Errorf("auth: nil AuthServiceClient for validator")
	}
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &GRPCValidator{client: client, timeout: timeout}, nil
}

// Validate calls auth ValidateToken with a bounded deadline.
func (v *GRPCValidator) Validate(ctx context.Context, accessToken string) (*ValidateResult, error) {
	callCtx, cancel := context.WithTimeout(ctx, v.timeout)
	defer cancel()

	resp, err := v.client.ValidateToken(callCtx, &authv1.ValidateTokenRequest{AccessToken: accessToken})
	if err != nil {
		return nil, mapValidateTokenError(err)
	}
	return mapValidateTokenResponse(resp)
}

func mapValidateTokenError(err error) error {
	if st, ok := status.FromError(err); ok && st.Code() == codes.Unauthenticated {
		return ErrInvalidToken
	}
	return fmt.Errorf("%w: %v", ErrAuthUnavailable, err)
}

func mapValidateTokenResponse(resp *authv1.ValidateTokenResponse) (*ValidateResult, error) {
	orgID, err := uuid.Parse(resp.GetOrgId())
	if err != nil {
		return nil, fmt.Errorf("%w: invalid org_id: %w", ErrAuthUnavailable, err)
	}
	result := &ValidateResult{
		OrgID:       orgID,
		Permissions: resp.GetPermissions(),
	}
	if resp.AgentId != nil {
		agentID, err := uuid.Parse(resp.GetAgentId())
		if err != nil {
			return nil, fmt.Errorf("%w: invalid agent_id: %w", ErrAuthUnavailable, err)
		}
		result.AgentID = agentID
	}
	if resp.UserId != nil {
		result.UserID = resp.GetUserId()
	}
	if resp.TokenId != nil {
		result.TokenID = resp.GetTokenId()
	}
	if resp.ExpiresAt != nil {
		result.ExpiresAt = resp.ExpiresAt.AsTime()
	}
	return result, nil
}
