package auth

import (
	"context"
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func runAgentVerifierCase(t *testing.T, tc agentVerifierCase) {
	t.Helper()
	const (
		bearer  = "ibex_pat_test"
		agentID = "550e8400-e29b-41d4-a716-446655440000"
		orgID   = "550e8400-e29b-41d4-a716-446655440001"
	)
	v, vErr := NewGRPCAgentVerifier(tc.client, time.Second)
	if vErr != nil {
		t.Fatalf("NewGRPCAgentVerifier: %v", vErr)
	}
	got, err := v.Verify(context.Background(), bearer, agentID, orgID)
	if tc.wantErr != nil {
		assertWantError(t, err, tc.wantErr)
		return
	}
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.ID != tc.want.ID {
		t.Fatalf("id: %s", got.ID)
	}
	if got.OrgID != tc.want.OrgID {
		t.Fatalf("org: %s", got.OrgID)
	}
	if got.Status != tc.want.Status {
		t.Fatalf("status: %s", got.Status)
	}
}

func TestGRPCAgentVerifier_Verify(t *testing.T) {
	t.Parallel()
	cases := append(agentVerifierOKCases(t), agentVerifierErrorCases()...)
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runAgentVerifierCase(t, tc)
		})
	}
}

func TestGRPCAgentVerifier_contextDeadline(t *testing.T) {
	t.Parallel()
	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	av, avErr := NewGRPCAgentVerifier(&mockAuthServiceClient{
		validateAgentFn: func(context.Context, *authv1.ValidateAgentRequest, ...grpc.CallOption) (*authv1.ValidateAgentResponse, error) {
			return nil, errors.New("transport error")
		},
	}, time.Second)
	if avErr != nil {
		t.Fatalf("NewGRPCAgentVerifier: %v", avErr)
	}
	_, err := av.Verify(ctx, "ibex_pat_test", "550e8400-e29b-41d4-a716-446655440000", "550e8400-e29b-41d4-a716-446655440001")
	if !errors.Is(err, ErrAgentVerifyUnavailable) {
		t.Fatalf("err = %v", err)
	}
}

func TestGRPCAgentVerifier_unknownGRPCCode(t *testing.T) {
	t.Parallel()
	av, avErr := NewGRPCAgentVerifier(&mockAuthServiceClient{
		validateAgentFn: func(context.Context, *authv1.ValidateAgentRequest, ...grpc.CallOption) (*authv1.ValidateAgentResponse, error) {
			return nil, status.Error(codes.Unknown, "unexpected")
		},
	}, time.Second)
	if avErr != nil {
		t.Fatalf("NewGRPCAgentVerifier: %v", avErr)
	}
	_, err := av.Verify(context.Background(), "ibex_pat_test", "550e8400-e29b-41d4-a716-446655440000", "550e8400-e29b-41d4-a716-446655440001")
	if !errors.Is(err, ErrAgentVerifyUnavailable) {
		t.Fatalf("err = %v", err)
	}
}

func TestNewGRPCAgentVerifier_defaultTimeout(t *testing.T) {
	t.Parallel()
	v, err := NewGRPCAgentVerifier(&mockAuthServiceClient{}, 0)
	if err != nil {
		t.Fatalf("NewGRPCAgentVerifier: %v", err)
	}
	if v.timeout != 50*time.Millisecond {
		t.Fatalf("timeout: %s", v.timeout)
	}
}

func TestNewGRPCAgentVerifier_nilClient(t *testing.T) {
	t.Parallel()

	var client authv1.AuthServiceClient
	_, err := NewGRPCAgentVerifier(client, time.Second)
	if err == nil {
		t.Fatal("expected error for nil client")
	}
}
