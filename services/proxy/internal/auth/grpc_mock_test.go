package auth

import (
	"context"
	"errors"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type mockAuthServiceClient struct {
	validateTokenFn func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error)
	validateAgentFn func(context.Context, *authv1.ValidateAgentRequest, ...grpc.CallOption) (*authv1.ValidateAgentResponse, error)
}

func (m *mockAuthServiceClient) ValidateToken(ctx context.Context, req *authv1.ValidateTokenRequest, opts ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
	if m.validateTokenFn != nil {
		return m.validateTokenFn(ctx, req, opts...)
	}
	return nil, status.Error(codes.Unimplemented, "not configured")
}

func (m *mockAuthServiceClient) ValidateAgent(ctx context.Context, req *authv1.ValidateAgentRequest, opts ...grpc.CallOption) (*authv1.ValidateAgentResponse, error) {
	if m.validateAgentFn != nil {
		return m.validateAgentFn(ctx, req, opts...)
	}
	return nil, status.Error(codes.Unimplemented, "not configured")
}

func (m *mockAuthServiceClient) CreateToken(context.Context, *authv1.CreateTokenRequest, ...grpc.CallOption) (*authv1.CreateTokenResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthServiceClient) RevokeToken(context.Context, *authv1.RevokeTokenRequest, ...grpc.CallOption) (*authv1.RevokeTokenResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthServiceClient) ListTokens(context.Context, *authv1.ListTokensRequest, ...grpc.CallOption) (*authv1.ListTokensResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthServiceClient) CreateProviderCredential(
	context.Context, *authv1.CreateProviderCredentialRequest, ...grpc.CallOption,
) (*authv1.CreateProviderCredentialResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthServiceClient) GetProviderCredential(
	context.Context, *authv1.GetProviderCredentialRequest, ...grpc.CallOption,
) (*authv1.GetProviderCredentialResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthServiceClient) DeleteProviderCredential(
	context.Context, *authv1.DeleteProviderCredentialRequest, ...grpc.CallOption,
) (*authv1.DeleteProviderCredentialResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func (m *mockAuthServiceClient) ListProviderCredentials(
	context.Context, *authv1.ListProviderCredentialsRequest, ...grpc.CallOption,
) (*authv1.ListProviderCredentialsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not used")
}

func assertWantError(t *testing.T, err, want error) {
	t.Helper()
	if !errors.Is(err, want) {
		t.Fatalf("err = %v, want %v", err, want)
	}
}
