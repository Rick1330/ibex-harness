package grpcserver

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func createTokenCases(t *testing.T, orgID string, expires *timestamppb.Timestamp) []createTokenCase {
	t.Helper()
	out := createTokenAuthzCases(t, orgID)
	out = append(out, createTokenFailureCases(t, orgID)...)
	return append(out, createTokenOKCases(t, orgID, expires)...)
}

func createTokenAuthzCases(t *testing.T, orgID string) []createTokenCase {
	t.Helper()
	return []createTokenCase{
		{
			name:     "unauthenticated",
			ctx:      context.Background(),
			req:      &authv1.CreateTokenRequest{OrgId: orgID, Name: "x"},
			wantCode: codes.Unauthenticated,
		},
		{
			name: "permission denied wrong org",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: uuid.NewString(), Permissions: permissions.Admin,
			}),
			req:      &authv1.CreateTokenRequest{OrgId: orgID, Name: "x"},
			wantCode: codes.PermissionDenied,
		},
		{
			name: "permission denied missing TokenCreate",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: orgID, Permissions: permissions.AgentDefault,
			}),
			req:      &authv1.CreateTokenRequest{OrgId: orgID, Name: "x"},
			wantCode: codes.PermissionDenied,
		},
	}
}

func createTokenFailureCases(t *testing.T, orgID string) []createTokenCase {
	t.Helper()
	return []createTokenCase{
		{
			name:     "invalid argument",
			ctx:      adminCtx(t, orgID),
			req:      &authv1.CreateTokenRequest{OrgId: orgID},
			wantCode: codes.InvalidArgument,
		},
		{
			name: "invalid expires_at",
			ctx:  adminCtx(t, orgID),
			req: &authv1.CreateTokenRequest{
				OrgId: orgID, Name: "pat",
				ExpiresAt: &timestamppb.Timestamp{Seconds: 0, Nanos: 1_000_000_000},
			},
			wantCode: codes.InvalidArgument,
		},
		{
			name: "internal error",
			ctx:  adminCtx(t, orgID),
			req:  &authv1.CreateTokenRequest{OrgId: orgID, Name: "pat"},
			tokens: &fakeTokenAPI{
				createFn: func(context.Context, service.CreateTokenInput) (service.CreateTokenResult, error) {
					return service.CreateTokenResult{}, errors.New("db down")
				},
			},
			wantCode: codes.Internal,
		},
	}
}

func createTokenOKCases(t *testing.T, orgID string, expires *timestamppb.Timestamp) []createTokenCase {
	t.Helper()
	return []createTokenCase{
		{
			name: "ok with expires_at",
			ctx:  adminCtx(t, orgID),
			req: &authv1.CreateTokenRequest{
				OrgId: orgID, Name: "pat", Permissions: permissions.AgentDefault,
				ExpiresAt: expires,
			},
			wantCode: codes.OK,
			checkIn:  assertCreateInputExpiresAt(expires),
		},
		{
			name: "ok",
			ctx:  adminCtx(t, orgID),
			req: &authv1.CreateTokenRequest{
				OrgId: orgID, Name: "pat", Permissions: permissions.AgentDefault,
			},
			wantCode: codes.OK,
		},
	}
}

func assertCreateInputExpiresAt(expires *timestamppb.Timestamp) func(*testing.T, service.CreateTokenInput) {
	return func(t *testing.T, in service.CreateTokenInput) {
		t.Helper()
		if in.ExpiresAt == nil {
			t.Fatal("ExpiresAt nil")
		}
		want := expires.AsTime()
		if !in.ExpiresAt.Equal(want) {
			t.Fatalf("ExpiresAt=%v want %v", in.ExpiresAt, want)
		}
	}
}
