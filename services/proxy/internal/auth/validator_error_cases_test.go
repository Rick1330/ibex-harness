package auth

import (
	"context"
	"errors"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func grpcValidatorErrorCases() []grpcValidatorCase {
	return []grpcValidatorCase{
		{
			name: "unauthenticated",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, status.Error(codes.Unauthenticated, "invalid token")
				},
			},
			wantErr: ErrInvalidToken,
		},
		{
			name: "unavailable",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, status.Error(codes.Unavailable, "down")
				},
			},
			wantErr: ErrAuthUnavailable,
		},
		{
			name: "deadline exceeded",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, status.Error(codes.DeadlineExceeded, "deadline")
				},
			},
			wantErr: ErrAuthUnavailable,
		},
		{
			name: "canceled",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, status.Error(codes.Canceled, "canceled")
				},
			},
			wantErr: ErrAuthUnavailable,
		},
		{
			name: "internal maps to unavailable",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, status.Error(codes.Internal, "boom")
				},
			},
			wantErr: ErrAuthUnavailable,
		},
		{
			name: "non status error",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, errors.New("transport reset")
				},
			},
			wantErr: ErrAuthUnavailable,
		},
		{
			name: "malformed org_id",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return &authv1.ValidateTokenResponse{OrgId: "not-a-uuid", Permissions: 1}, nil
				},
			},
			wantErr: ErrAuthUnavailable,
		},
		{
			name: "malformed agent_id",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					bad := "bad-agent"
					return &authv1.ValidateTokenResponse{
						OrgId: "550e8400-e29b-41d4-a716-446655440001", Permissions: 1, AgentId: &bad,
					}, nil
				},
			},
			wantErr: ErrAuthUnavailable,
		},
	}
}
