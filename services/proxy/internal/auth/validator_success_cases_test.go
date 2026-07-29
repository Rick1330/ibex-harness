package auth

import (
	"context"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/google/uuid"
	"google.golang.org/grpc"
)

func grpcValidatorSuccessCases(t *testing.T) []grpcValidatorCase {
	t.Helper()
	const (
		orgID       = "550e8400-e29b-41d4-a716-446655440001"
		agentID     = "550e8400-e29b-41d4-a716-446655440000"
		userID      = "550e8400-e29b-41d4-a716-446655440002"
		fixtureRef  = "test-token-id-1"
		accessToken = "ibex_pat_test"
	)
	return []grpcValidatorCase{
		{
			name: "ok minimal fields",
			client: &mockAuthServiceClient{
				validateTokenFn: func(_ context.Context, req *authv1.ValidateTokenRequest, _ ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					if req.GetAccessToken() != accessToken {
						t.Fatalf("token: %q", req.GetAccessToken())
					}
					return &authv1.ValidateTokenResponse{OrgId: orgID, Permissions: 42}, nil
				},
			},
			want: &ValidateResult{OrgID: uuid.MustParse(orgID), Permissions: 42},
		},
		{
			name: "ok optional fields",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return &authv1.ValidateTokenResponse{
						OrgId: orgID, Permissions: 7,
						AgentId: strPtr(agentID), UserId: strPtr(userID), TokenId: strPtr(fixtureRef),
					}, nil
				},
			},
			want: &ValidateResult{
				OrgID: uuid.MustParse(orgID), Permissions: 7,
				AgentID: uuid.MustParse(agentID), UserID: userID, TokenID: fixtureRef,
			},
		},
	}
}
