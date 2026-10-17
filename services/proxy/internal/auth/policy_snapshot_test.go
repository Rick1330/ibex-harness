package auth

import (
	"context"
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func TestUnit_GRPCPolicySnapshotClient_ConstructorGuards(t *testing.T) {
	t.Parallel()
	if _, err := NewGRPCPolicySnapshotClient(nil, time.Second); err == nil {
		t.Fatal("expected nil client error")
	}
	var typedNil *mockAuthServiceClient
	if _, err := NewGRPCPolicySnapshotClient(typedNil, time.Second); err == nil {
		t.Fatal("expected typed-nil client error")
	}
	client, err := NewGRPCPolicySnapshotClient(&mockAuthServiceClient{}, 0)
	if err != nil {
		t.Fatalf("NewGRPCPolicySnapshotClient: %v", err)
	}
	if client.timeout != 50*time.Millisecond {
		t.Fatalf("timeout = %v want 50ms default", client.timeout)
	}
}

func TestUnit_GRPCPolicySnapshotClient_IssueForwardsBearerAndAgent(t *testing.T) {
	t.Parallel()
	var gotReq *authv1.IssuePolicySnapshotRequest
	var gotAuth []string
	var hadDeadline bool
	client, err := NewGRPCPolicySnapshotClient(&mockAuthServiceClient{
		issuePolicySnapshotFn: func(ctx context.Context, req *authv1.IssuePolicySnapshotRequest, _ ...grpc.CallOption) (*authv1.IssuePolicySnapshotResponse, error) {
			gotReq = req
			if md, ok := metadata.FromOutgoingContext(ctx); ok {
				gotAuth = md.Get("authorization")
			}
			_, hadDeadline = ctx.Deadline()
			return &authv1.IssuePolicySnapshotResponse{Envelope: &authv1.PolicySnapshotEnvelope{
				Algorithm: "RS256", KeyId: "v1", Payload: []byte("payload"), Signature: []byte("sig"),
			}}, nil
		},
	}, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	env, err := client.Issue(context.Background(), "ibex_pat_test", "agent-1")
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}
	if gotReq.GetAgentId() != "agent-1" {
		t.Fatalf("agent id = %q", gotReq.GetAgentId())
	}
	if len(gotAuth) != 1 || gotAuth[0] != "Bearer ibex_pat_test" {
		t.Fatalf("authorization metadata = %v", gotAuth)
	}
	if !hadDeadline {
		t.Fatal("call context missing deadline")
	}
	if env.Algorithm != "RS256" || env.KeyID != "v1" || string(env.Payload) != "payload" || string(env.Signature) != "sig" {
		t.Fatalf("envelope = %+v", env)
	}
}

func TestUnit_GRPCPolicySnapshotClient_IssueErrors(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		err  error
		want error
	}{
		{"unauthenticated", status.Error(codes.Unauthenticated, "bad token"), ErrInvalidToken},
		{"permission denied", status.Error(codes.PermissionDenied, "nope"), ErrPolicySnapshotDenied},
		{"invalid argument", status.Error(codes.InvalidArgument, "bad agent"), ErrPolicySnapshotDenied},
		{"failed precondition", status.Error(codes.FailedPrecondition, "no issuer"), ErrPolicySnapshotDenied},
		{"unavailable", status.Error(codes.Unavailable, "down"), ErrPolicySnapshotUnavailable},
		{"deadline", status.Error(codes.DeadlineExceeded, "slow"), ErrPolicySnapshotUnavailable},
		{"unknown", errors.New("boom"), ErrPolicySnapshotUnavailable},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			client, err := NewGRPCPolicySnapshotClient(&mockAuthServiceClient{
				issuePolicySnapshotFn: func(context.Context, *authv1.IssuePolicySnapshotRequest, ...grpc.CallOption) (*authv1.IssuePolicySnapshotResponse, error) {
					return nil, tc.err
				},
			}, time.Second)
			if err != nil {
				t.Fatal(err)
			}
			_, err = client.Issue(context.Background(), "ibex_pat_test", "agent-1")
			if !errors.Is(err, tc.want) {
				t.Fatalf("err = %v want %v", err, tc.want)
			}
		})
	}
}

func TestUnit_GRPCPolicySnapshotClient_RejectsIncompleteEnvelope(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		resp *authv1.IssuePolicySnapshotResponse
	}{
		{"nil envelope", &authv1.IssuePolicySnapshotResponse{}},
		{"empty payload", &authv1.IssuePolicySnapshotResponse{Envelope: &authv1.PolicySnapshotEnvelope{Algorithm: "RS256", KeyId: "v1", Signature: []byte("sig")}}},
		{"empty signature", &authv1.IssuePolicySnapshotResponse{Envelope: &authv1.PolicySnapshotEnvelope{Algorithm: "RS256", KeyId: "v1", Payload: []byte("p")}}},
		{"empty algorithm", &authv1.IssuePolicySnapshotResponse{Envelope: &authv1.PolicySnapshotEnvelope{KeyId: "v1", Payload: []byte("p"), Signature: []byte("s")}}},
		{"empty key id", &authv1.IssuePolicySnapshotResponse{Envelope: &authv1.PolicySnapshotEnvelope{Algorithm: "RS256", Payload: []byte("p"), Signature: []byte("s")}}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			client, err := NewGRPCPolicySnapshotClient(&mockAuthServiceClient{
				issuePolicySnapshotFn: func(context.Context, *authv1.IssuePolicySnapshotRequest, ...grpc.CallOption) (*authv1.IssuePolicySnapshotResponse, error) {
					return tc.resp, nil
				},
			}, time.Second)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := client.Issue(context.Background(), "ibex_pat_test", "agent-1"); !errors.Is(err, ErrPolicySnapshotUnavailable) {
				t.Fatalf("err = %v want ErrPolicySnapshotUnavailable", err)
			}
		})
	}
}
