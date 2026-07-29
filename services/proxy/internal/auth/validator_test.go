package auth

import (
	"context"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
)

func strPtr(s string) *string { return &s }

func runGRPCValidatorCase(t *testing.T, tc grpcValidatorCase, accessToken string) {
	t.Helper()
	v, vErr := NewGRPCValidator(tc.client, time.Second)
	if vErr != nil {
		t.Fatalf("NewGRPCValidator: %v", vErr)
	}
	got, err := v.Validate(context.Background(), accessToken)
	if tc.wantErr != nil {
		assertWantError(t, err, tc.wantErr)
		return
	}
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	assertValidateResult(t, got, tc.want)
}

func assertValidateResult(t *testing.T, got, want *ValidateResult) {
	t.Helper()
	if got.OrgID != want.OrgID {
		t.Fatalf("org: %s", got.OrgID)
	}
	if got.Permissions != want.Permissions {
		t.Fatalf("perms: %d", got.Permissions)
	}
	if got.AgentID != want.AgentID {
		t.Fatalf("agent: %s", got.AgentID)
	}
	if got.UserID != want.UserID {
		t.Fatalf("user: %s", got.UserID)
	}
	if got.TokenID != want.TokenID {
		t.Fatalf("token: %s", got.TokenID)
	}
}

func TestGRPCValidator_Validate(t *testing.T) {
	t.Parallel()
	cases := append(grpcValidatorSuccessCases(t), grpcValidatorErrorCases()...)
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runGRPCValidatorCase(t, tc, "ibex_pat_test")
		})
	}
}

func TestNewGRPCValidator_defaultTimeout(t *testing.T) {
	t.Parallel()
	client := &mockAuthServiceClient{
		validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
			return &authv1.ValidateTokenResponse{
				OrgId: "550e8400-e29b-41d4-a716-446655440099", Permissions: 1,
			}, nil
		},
	}

	v, err := NewGRPCValidator(client, 0)
	if err != nil {
		t.Fatalf("NewGRPCValidator: %v", err)
	}

	if v.timeout != 50*time.Millisecond {
		t.Fatalf("timeout: %s", v.timeout)
	}
}

func TestNewGRPCValidator_nilClient(t *testing.T) {
	t.Parallel()

	var client authv1.AuthServiceClient
	_, err := NewGRPCValidator(client, time.Second)
	if err == nil {
		t.Fatal("expected error for nil client")
	}
}
