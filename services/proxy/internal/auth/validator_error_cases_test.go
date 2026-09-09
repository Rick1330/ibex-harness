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
	out := make([]grpcValidatorCase, 0, 9)
	out = append(out, grpcStatusErrorCases()...)
	out = append(out, grpcPayloadErrorCases()...)
	return out
}

func grpcStatusErrorCases() []grpcValidatorCase {
	return []grpcValidatorCase{
		statusCase("unauthenticated", codes.Unauthenticated, "invalid token", ErrInvalidToken),
		statusCase("org suspended", codes.PermissionDenied, "organization is suspended", ErrOrgSuspended),
		statusCase("unavailable", codes.Unavailable, "down", ErrAuthUnavailable),
		statusCase("deadline exceeded", codes.DeadlineExceeded, "deadline", ErrAuthUnavailable),
		statusCase("canceled", codes.Canceled, "canceled", ErrAuthUnavailable),
		statusCase("internal maps to unavailable", codes.Internal, "boom", ErrAuthUnavailable),
		{
			name: "non status error",
			client: &mockAuthServiceClient{
				validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
					return nil, errors.New("transport reset")
				},
			},
			wantErr: ErrAuthUnavailable,
		},
	}
}

func grpcPayloadErrorCases() []grpcValidatorCase {
	badAgent := "bad-agent"
	return []grpcValidatorCase{
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
					return &authv1.ValidateTokenResponse{
						OrgId: "550e8400-e29b-41d4-a716-446655440001", Permissions: 1, AgentId: &badAgent,
					}, nil
				},
			},
			wantErr: ErrAuthUnavailable,
		},
	}
}

func statusCase(name string, code codes.Code, msg string, want error) grpcValidatorCase {
	return grpcValidatorCase{
		name: name,
		client: &mockAuthServiceClient{
			validateTokenFn: func(context.Context, *authv1.ValidateTokenRequest, ...grpc.CallOption) (*authv1.ValidateTokenResponse, error) {
				return nil, status.Error(code, msg)
			},
		},
		wantErr: want,
	}
}
