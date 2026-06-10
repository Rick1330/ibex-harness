package healthcheck

import (
	"context"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type mockAuthClient struct {
	err error
}

func (m *mockAuthClient) ValidateToken(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
	return nil, m.err
}

func (m *mockAuthClient) ValidateAgent(context.Context, *authv1.ValidateAgentRequest, ...grpc.CallOption) (*authv1.ValidateAgentResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthClient) CreateToken(context.Context, *authv1.CreateTokenRequest, ...grpc.CallOption) (*authv1.CreateTokenResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthClient) RevokeToken(context.Context, *authv1.RevokeTokenRequest, ...grpc.CallOption) (*authv1.RevokeTokenResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthClient) ListTokens(context.Context, *authv1.ListTokensRequest, ...grpc.CallOption) (*authv1.ListTokensResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func TestAuthGRPC_UnauthenticatedIsHealthy(t *testing.T) {
	t.Parallel()
	client := &mockAuthClient{err: status.Error(codes.Unauthenticated, "invalid token")}
	err := AuthGRPC(client, time.Second)(context.Background())
	if err != nil {
		t.Fatalf("expected nil, got %v", err)
	}
}

func TestAuthGRPC_UnavailableFails(t *testing.T) {
	t.Parallel()
	client := &mockAuthClient{err: status.Error(codes.Unavailable, "down")}
	err := AuthGRPC(client, time.Second)(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestAuthGRPC_NilClient(t *testing.T) {
	t.Parallel()
	err := AuthGRPC(nil, time.Second)(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
}
