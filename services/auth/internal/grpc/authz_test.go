package grpcserver

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestCallerFromContext(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		setup  func(context.Context) context.Context
		wantOK bool
		want   CallerContext
	}{
		{
			name: "missing caller",
			setup: func(ctx context.Context) context.Context {
				return ctx
			},
			wantOK: false,
		},
		{
			name: "caller attached",
			setup: func(ctx context.Context) context.Context {
				return ContextWithCaller(ctx, CallerContext{
					OrgID: "org-1", TokenID: "tok-1", UserID: "user-1", Permissions: 7,
				})
			},
			wantOK: true,
			want: CallerContext{
				OrgID: "org-1", TokenID: "tok-1", UserID: "user-1", Permissions: 7,
			},
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, ok := CallerFromContext(tc.setup(context.Background()))

			if ok != tc.wantOK {
				t.Fatalf("ok: got %v want %v", ok, tc.wantOK)
			}
			if !tc.wantOK {
				return
			}
			if got != tc.want {
				t.Fatalf("caller: got %+v want %+v", got, tc.want)
			}
		})
	}
}

func TestRequireOrgAndPermission(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		ctx      context.Context
		orgID    string
		required int64
		wantCode codes.Code
	}{
		{
			name:     "missing caller",
			ctx:      context.Background(),
			orgID:    "org-1",
			required: permissions.TokenCreate,
			wantCode: codes.Unauthenticated,
		},
		{
			name: "org mismatch",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: "org-a", Permissions: permissions.Admin,
			}),
			orgID:    "org-b",
			required: permissions.TokenCreate,
			wantCode: codes.PermissionDenied,
		},
		{
			name: "missing permission",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: "org-1", Permissions: permissions.ReadOnly,
			}),
			orgID:    "org-1",
			required: permissions.TokenCreate,
			wantCode: codes.PermissionDenied,
		},
		{
			name: "allowed",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: "org-1", Permissions: permissions.Admin,
			}),
			orgID:    "org-1",
			required: permissions.TokenCreate,
			wantCode: codes.OK,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			err := RequireOrgAndPermission(tc.ctx, OrgPermissionCheck{OrgID: tc.orgID, Required: tc.required})

			if tc.wantCode == codes.OK {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				return
			}
			if status.Code(err) != tc.wantCode {
				t.Fatalf("code: got %v want %v", status.Code(err), tc.wantCode)
			}
		})
	}
}

func TestCanRevoke(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		caller    CallerContext
		orgID     string
		tokenID   string
		wantAllow bool
	}{
		{
			name:      "org mismatch",
			caller:    CallerContext{OrgID: "org-a", Permissions: permissions.Admin},
			orgID:     "org-b",
			tokenID:   "tok-1",
			wantAllow: false,
		},
		{
			name:      "token revoke permission",
			caller:    CallerContext{OrgID: "org-1", Permissions: permissions.TokenRevoke},
			orgID:     "org-1",
			tokenID:   "other-token",
			wantAllow: true,
		},
		{
			name:      "self revoke without token revoke bit",
			caller:    CallerContext{OrgID: "org-1", TokenID: "self-token", Permissions: permissions.ReadOnly},
			orgID:     "org-1",
			tokenID:   "self-token",
			wantAllow: true,
		},
		{
			name:      "cannot revoke other token without permission",
			caller:    CallerContext{OrgID: "org-1", TokenID: "self-token", Permissions: permissions.ReadOnly},
			orgID:     "org-1",
			tokenID:   "other-token",
			wantAllow: false,
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got := CanRevoke(tc.caller, RevokeTarget{OrgID: tc.orgID, TokenID: tc.tokenID})

			if got != tc.wantAllow {
				t.Fatalf("CanRevoke = %v, want %v", got, tc.wantAllow)
			}
		})
	}
}
