package auth

import (
	"context"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// GRPCValidator validates tokens via AuthService.ValidateToken.
type GRPCValidator struct {
	client  authv1.AuthServiceClient
	timeout time.Duration
}

// NewGRPCValidator creates a validator using the given client and per-call timeout.
func NewGRPCValidator(client authv1.AuthServiceClient, timeout time.Duration) *GRPCValidator {
	if timeout <= 0 {
		timeout = 50 * time.Millisecond
	}
	return &GRPCValidator{client: client, timeout: timeout}
}

// Validate calls auth ValidateToken with a bounded deadline.
func (v *GRPCValidator) Validate(ctx context.Context, accessToken string) (*ValidateResult, error) {
	callCtx, cancel := context.WithTimeout(ctx, v.timeout)
	defer cancel()

	resp, err := v.client.ValidateToken(callCtx, &authv1.ValidateTokenRequest{AccessToken: accessToken})
	if err != nil {
		return nil, mapValidateTokenError(err)
	}
	return mapValidateTokenResponse(resp), nil
}

func mapValidateTokenError(err error) error {
	if st, ok := status.FromError(err); ok && st.Code() == codes.Unauthenticated {
		return ErrInvalidToken
	}
	return ErrAuthUnavailable
}

func mapValidateTokenResponse(resp *authv1.ValidateTokenResponse) *ValidateResult {
	result := &ValidateResult{
		OrgID:       resp.GetOrgId(),
		Permissions: resp.GetPermissions(),
	}
	if resp.AgentId != nil {
		result.AgentID = resp.GetAgentId()
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
	return result
}
