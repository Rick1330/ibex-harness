package grpcserver

import (
	"context"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type stubTokenValidator struct {
	fn func(context.Context, string) (*authv1.ValidateTokenResponse, error)
}

func (s *stubTokenValidator) Validate(ctx context.Context, accessToken string) (*authv1.ValidateTokenResponse, error) {
	return s.fn(ctx, accessToken)
}

func TestAuthzUnaryInterceptor_skipsValidateToken(t *testing.T) {
	t.Parallel()

	called := false
	ic := AuthzUnaryInterceptor(&stubTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
		t.Fatal("validator should not run for ValidateToken")
		return nil, nil
	}})

	_, err := ic(context.Background(), &authv1.CreateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/ValidateToken"},
		func(ctx context.Context, req any) (any, error) {
			called = true
			return &authv1.ValidateTokenResponse{}, nil
		},
	)
	if err != nil || !called {
		t.Fatalf("err=%v called=%v", err, called)
	}
}

func TestAuthzUnaryInterceptor_validBearer(t *testing.T) {
	t.Parallel()

	tokenID := "tok-1"
	userID := "user-1"
	ic := AuthzUnaryInterceptor(&stubTokenValidator{fn: func(_ context.Context, bearer string) (*authv1.ValidateTokenResponse, error) {
		if bearer != "secret" {
			t.Fatalf("bearer: %q", bearer)
		}
		return &authv1.ValidateTokenResponse{
			OrgId: "org-1", Permissions: 7, TokenId: &tokenID, UserId: &userID,
		}, nil
	}})

	ctx := metadata.NewIncomingContext(context.Background(), metadata.Pairs("authorization", "Bearer secret"))
	var gotCaller CallerContext
	_, err := ic(ctx, &authv1.CreateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/CreateToken"},
		func(ctx context.Context, req any) (any, error) {
			c, ok := CallerFromContext(ctx)
			if !ok {
				t.Fatal("missing caller")
			}
			gotCaller = c
			return &authv1.CreateTokenResponse{}, nil
		},
	)
	if err != nil {
		t.Fatalf("interceptor: %v", err)
	}
	if gotCaller.OrgID != "org-1" {
		t.Fatalf("org: %s", gotCaller.OrgID)
	}
	if gotCaller.TokenID != tokenID {
		t.Fatalf("token: %s", gotCaller.TokenID)
	}
	if gotCaller.UserID != userID {
		t.Fatalf("user: %s", gotCaller.UserID)
	}
}

func TestBearerFromMetadata(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		ctx      context.Context
		wantCode codes.Code
		wantTok  string
	}{
		{
			name:     "missing metadata",
			ctx:      context.Background(),
			wantCode: codes.Unauthenticated,
		},
		{
			name:     "missing authorization header",
			ctx:      metadata.NewIncomingContext(context.Background(), metadata.Pairs("other", "x")),
			wantCode: codes.Unauthenticated,
		},
		{
			name:     "invalid prefix",
			ctx:      metadata.NewIncomingContext(context.Background(), metadata.Pairs("authorization", "Token x")),
			wantCode: codes.Unauthenticated,
		},
		{
			name:     "empty bearer",
			ctx:      metadata.NewIncomingContext(context.Background(), metadata.Pairs("authorization", "Bearer ")),
			wantCode: codes.Unauthenticated,
		},
		{
			name:     "ok",
			ctx:      metadata.NewIncomingContext(context.Background(), metadata.Pairs("authorization", "Bearer  pat-token ")),
			wantCode: codes.OK,
			wantTok:  "pat-token",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, err := bearerFromMetadata(tc.ctx)

			if tc.wantCode == codes.OK {
				if err != nil || got != tc.wantTok {
					t.Fatalf("got %q err=%v", got, err)
				}
				return
			}
			if status.Code(err) != tc.wantCode {
				t.Fatalf("code: got %v want %v", status.Code(err), tc.wantCode)
			}
		})
	}
}

func TestAuthzUnaryInterceptor_invalidBearer(t *testing.T) {
	t.Parallel()

	ic := AuthzUnaryInterceptor(&stubTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
		return nil, token.ErrUnauthenticated
	}})

	ctx := metadata.NewIncomingContext(context.Background(), metadata.Pairs("authorization", "Bearer bad"))
	_, err := ic(ctx, &authv1.CreateTokenRequest{},
		&grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/CreateToken"},
		func(context.Context, any) (any, error) { return nil, nil },
	)
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestAuthzUnaryInterceptor_serviceTokenIsLimitedToLifecycleMethods(t *testing.T) {
	t.Parallel()

	called := false
	ic := AuthzUnaryInterceptorWithServiceToken(&stubTokenValidator{fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
		t.Fatal("PAT validator must not run for a valid service-token lifecycle call")
		return nil, nil
	}}, "service-secret")
	ctx := metadata.NewIncomingContext(context.Background(), metadata.Pairs(serviceTokenMetadataKey, "service-secret"))
	_, err := ic(ctx, &authv1.ValidateOperatorSessionRequest{}, &grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/ValidateOperatorSession"}, func(context.Context, any) (any, error) {
		called = true
		return &authv1.ValidateOperatorSessionResponse{}, nil
	})
	if err != nil || !called {
		t.Fatalf("service lifecycle call: err=%v called=%v", err, called)
	}

	called = false
	_, err = ic(ctx, &authv1.CreateTokenRequest{}, &grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/CreateToken"}, func(context.Context, any) (any, error) {
		called = true
		return nil, nil
	})
	if status.Code(err) != codes.Unauthenticated || called {
		t.Fatalf("service token must not authorize management RPC: err=%v called=%v", err, called)
	}
}

func TestMetricsUnaryInterceptor(t *testing.T) {
	t.Parallel()

	reg := testAuthRegistry()
	ic := MetricsUnaryInterceptor(reg)

	_, err := ic(context.Background(), nil,
		&grpc.UnaryServerInfo{FullMethod: "/ibex.auth.v1.AuthService/ValidateToken"},
		func(context.Context, any) (any, error) {
			return nil, status.Error(codes.InvalidArgument, "bad")
		},
	)
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("handler err: %v", err)
	}
}

func TestShortGRPCMethod(t *testing.T) {
	t.Parallel()

	if got := shortGRPCMethod("/ibex.auth.v1.AuthService/ValidateToken"); got != "ValidateToken" {
		t.Fatalf("got %q", got)
	}
	if got := shortGRPCMethod("ValidateToken"); got != "ValidateToken" {
		t.Fatalf("got %q", got)
	}
}
