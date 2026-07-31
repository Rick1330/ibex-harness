package grpcserver

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type validateTokenCase struct {
	name     string
	fn       func(context.Context, string) (*authv1.ValidateTokenResponse, error)
	wantCode codes.Code
}

func runValidateTokenCase(t *testing.T, tc validateTokenCase) {
	t.Helper()

	s := newTestServer(t, &fakeTokenValidator{fn: tc.fn}, &fakeTokenAPI{}, &fakeAgentAPI{})
	resp, err := s.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{AccessToken: "tok"})
	assertOKOrGRPCCode(t, err, tc.wantCode, func() {
		if resp.GetOrgId() != "org-1" || resp.GetPermissions() != 7 {
			t.Fatalf("response: %+v", resp)
		}
	})
}

func TestServer_ValidateToken(t *testing.T) {
	t.Parallel()
	for _, tc := range []validateTokenCase{
		{
			name: "unauthenticated",
			fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
				return nil, token.ErrUnauthenticated
			},
			wantCode: codes.Unauthenticated,
		},
		{
			name: "internal error",
			fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
				return nil, errors.New("db down")
			},
			wantCode: codes.Internal,
		},
		{
			name: "ok",
			fn: func(context.Context, string) (*authv1.ValidateTokenResponse, error) {
				return &authv1.ValidateTokenResponse{OrgId: "org-1", Permissions: 7}, nil
			},
			wantCode: codes.OK,
		},
	} {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runValidateTokenCase(t, tc)
		})
	}
}

type createTokenCase struct {
	name     string
	ctx      context.Context
	req      *authv1.CreateTokenRequest
	tokens   *fakeTokenAPI
	wantCode codes.Code
	checkIn  func(*testing.T, service.CreateTokenInput)
}

func runCreateTokenCase(t *testing.T, tc createTokenCase) {
	t.Helper()

	tokens := tc.tokens
	if tokens == nil {
		tokens = &fakeTokenAPI{}
	}
	if tc.checkIn != nil {
		baseCreate := tokens.createFn
		tokens.createFn = func(ctx context.Context, in service.CreateTokenInput) (service.CreateTokenResult, error) {
			tc.checkIn(t, in)
			if baseCreate != nil {
				return baseCreate(ctx, in)
			}
			return (&fakeTokenAPI{}).CreateToken(ctx, in)
		}
	}
	s := newTestServer(t, &fakeTokenValidator{}, tokens, &fakeAgentAPI{})
	resp, err := s.CreateToken(tc.ctx, tc.req)
	assertOKOrGRPCCode(t, err, tc.wantCode, func() {
		if resp.GetTokenId() == "" || resp.GetPlaintext() == "" {
			t.Fatalf("incomplete response: %+v", resp)
		}
	})
}

func TestServer_CreateToken(t *testing.T) {
	t.Parallel()

	orgID := uuid.NewString()
	expires := timestamppb.New(time.Now().UTC().Add(time.Hour))
	for _, tc := range []createTokenCase{
		{
			name:     "unauthenticated",
			ctx:      context.Background(),
			req:      &authv1.CreateTokenRequest{OrgId: orgID, Name: "x"},
			wantCode: codes.Unauthenticated,
		},
		{
			name: "permission denied wrong org",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: uuid.NewString(), Permissions: permissions.Admin,
			}),
			req:      &authv1.CreateTokenRequest{OrgId: orgID, Name: "x"},
			wantCode: codes.PermissionDenied,
		},
		{
			name: "permission denied missing TokenCreate",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: orgID, Permissions: permissions.AgentDefault,
			}),
			req:      &authv1.CreateTokenRequest{OrgId: orgID, Name: "x"},
			wantCode: codes.PermissionDenied,
		},
		{
			name:     "invalid argument",
			ctx:      adminCtx(t, orgID),
			req:      &authv1.CreateTokenRequest{OrgId: orgID},
			wantCode: codes.InvalidArgument,
		},
		{
			name: "invalid expires_at",
			ctx:  adminCtx(t, orgID),
			req: &authv1.CreateTokenRequest{
				OrgId: orgID, Name: "pat",
				ExpiresAt: &timestamppb.Timestamp{Seconds: 0, Nanos: 1_000_000_000},
			},
			wantCode: codes.InvalidArgument,
		},
		{
			name: "internal error",
			ctx:  adminCtx(t, orgID),
			req:  &authv1.CreateTokenRequest{OrgId: orgID, Name: "pat"},
			tokens: &fakeTokenAPI{
				createFn: func(context.Context, service.CreateTokenInput) (service.CreateTokenResult, error) {
					return service.CreateTokenResult{}, errors.New("db down")
				},
			},
			wantCode: codes.Internal,
		},
		{
			name: "ok with expires_at",
			ctx:  adminCtx(t, orgID),
			req: &authv1.CreateTokenRequest{
				OrgId: orgID, Name: "pat", Permissions: permissions.AgentDefault,
				ExpiresAt: expires,
			},
			wantCode: codes.OK,
			checkIn: func(t *testing.T, in service.CreateTokenInput) {
				t.Helper()
				if in.ExpiresAt == nil {
					t.Fatal("ExpiresAt nil")
				}
				want := expires.AsTime()
				if !in.ExpiresAt.Equal(want) {
					t.Fatalf("ExpiresAt=%v want %v", in.ExpiresAt, want)
				}
			},
		},
		{
			name: "ok",
			ctx:  adminCtx(t, orgID),
			req: &authv1.CreateTokenRequest{
				OrgId: orgID, Name: "pat", Permissions: permissions.AgentDefault,
			},
			wantCode: codes.OK,
		},
	} {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runCreateTokenCase(t, tc)
		})
	}
}

type revokeTokenCase struct {
	name     string
	ctx      context.Context
	req      *authv1.RevokeTokenRequest
	tokens   *fakeTokenAPI
	wantCode codes.Code
}

func runRevokeTokenCase(t *testing.T, tc revokeTokenCase) {
	t.Helper()

	tokens := tc.tokens
	if tokens == nil {
		tokens = &fakeTokenAPI{}
	}
	s := newTestServer(t, &fakeTokenValidator{}, tokens, &fakeAgentAPI{})

	_, err := s.RevokeToken(tc.ctx, tc.req)
	if tc.wantCode == codes.OK {
		if err != nil {
			t.Fatalf("RevokeToken: %v", err)
		}
		return
	}
	assertGRPCCode(t, err, tc.wantCode)
}

func TestServer_RevokeToken(t *testing.T) {
	t.Parallel()
	for _, tc := range revokeTokenCases(t) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runRevokeTokenCase(t, tc)
		})
	}
}

func TestServer_ListTokens(t *testing.T) {
	t.Parallel()
	orgID := uuid.NewString()
	for _, tc := range listTokensCases(t, orgID) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runListTokensCase(t, orgID, tc)
		})
	}
}
