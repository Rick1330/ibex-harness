package grpcserver

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
)

func revokeTokenCases(t *testing.T) []revokeTokenCase {
	t.Helper()
	orgID, tokenID := uuid.NewString(), uuid.NewString()
	selfTokenID := uuid.NewString()
	return []revokeTokenCase{
		{
			name: "unauthenticated", ctx: context.Background(),
			req: revokeTokenRequest(orgID, tokenID), wantCode: codes.Unauthenticated,
		},
		{
			name: "cross tenant forbidden",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: uuid.NewString(), Permissions: permissions.Admin,
			}),
			req: revokeTokenRequest(orgID, tokenID), wantCode: codes.PermissionDenied,
		},
		{
			name: "permission denied",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: orgID, TokenID: uuid.NewString(), Permissions: permissions.ReadOnly,
			}),
			req: revokeTokenRequest(orgID, tokenID), wantCode: codes.PermissionDenied,
		},
		{
			name: "not found in repo", ctx: adminCtx(t, orgID),
			req: revokeTokenRequest(orgID, tokenID),
			tokens: &fakeTokenAPI{
				revokeFn: func(context.Context, service.RevokeTokenParams) error {
					return service.ErrTokenNotFound
				},
			},
			wantCode: codes.NotFound,
		},
		{
			name: "internal error", ctx: adminCtx(t, orgID),
			req: revokeTokenRequest(orgID, tokenID),
			tokens: &fakeTokenAPI{
				revokeFn: func(context.Context, service.RevokeTokenParams) error {
					return errors.New("db down")
				},
			},
			wantCode: codes.Internal,
		},
		{
			name: "self revoke ok",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: orgID, TokenID: selfTokenID, Permissions: permissions.ReadOnly,
			}),
			req: revokeTokenRequest(orgID, selfTokenID), tokens: &fakeTokenAPI{},
			wantCode: codes.OK,
		},
		{
			name: "admin revoke ok", ctx: adminCtx(t, orgID),
			req: revokeTokenRequest(orgID, tokenID), tokens: &fakeTokenAPI{},
			wantCode: codes.OK,
		},
	}
}
