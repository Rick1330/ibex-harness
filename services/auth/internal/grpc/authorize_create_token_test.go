package grpcserver

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestUnit_AuthorizeCreateTokenPermissions(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name       string
		caller     int64
		requested  int64
		wantCode   codes.Code
		wantNilErr bool
	}{
		{
			name:       "admin_mints_agent_default",
			caller:     permissions.Admin,
			requested:  permissions.AgentDefault,
			wantNilErr: true,
		},
		{
			name:       "equal_bits_ok",
			caller:     permissions.TokenCreate | permissions.AgentDefault,
			requested:  permissions.TokenCreate | permissions.AgentDefault,
			wantNilErr: true,
		},
		{
			name:       "zero_requested_ok",
			caller:     permissions.TokenCreate,
			requested:  0,
			wantNilErr: true,
		},
		{
			name:      "token_create_only_cannot_mint_admin",
			caller:    permissions.TokenCreate,
			requested: permissions.Admin,
			wantCode:  codes.PermissionDenied,
		},
		{
			name:      "cannot_mint_bits_caller_lacks",
			caller:    permissions.TokenCreate | permissions.AgentDefault,
			requested: permissions.BillingManage,
			wantCode:  codes.PermissionDenied,
		},
		{
			name:      "reserved_high_bits_invalid",
			caller:    permissions.Admin,
			requested: int64(1 << 60),
			wantCode:  codes.InvalidArgument,
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			err := authorizeCreateTokenPermissions(tc.caller, tc.requested)

			if tc.wantNilErr {
				if err != nil {
					t.Fatalf("err=%v", err)
				}
				return
			}
			if status.Code(err) != tc.wantCode {
				t.Fatalf("code=%v want %v err=%v", status.Code(err), tc.wantCode, err)
			}
			if status.Convert(err).Message() == "" {
				t.Fatal("expected opaque status message")
			}
		})
	}
}
