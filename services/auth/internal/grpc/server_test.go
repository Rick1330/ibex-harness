package grpcserver

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
)

type validateTokenCase struct {
	name     string
	fn       func(context.Context, string) (*authv1.ValidateTokenResponse, error)
	wantCode codes.Code
}

func runValidateTokenCase(t *testing.T, tc validateTokenCase) {
	t.Helper()

	s := newTestServer(t, &fakeTokenValidator{fn: tc.fn}, &fakeTokenRepo{}, &fakeAgentsStore{})
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
	wantCode codes.Code
}

func runCreateTokenCase(t *testing.T, tc createTokenCase) {
	t.Helper()

	s := newTestServer(t, &fakeTokenValidator{}, &fakeTokenRepo{}, &fakeAgentsStore{})
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
			name:     "invalid argument",
			ctx:      adminCtx(t, orgID),
			req:      &authv1.CreateTokenRequest{OrgId: orgID},
			wantCode: codes.InvalidArgument,
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
	repo     *fakeTokenRepo
	wantCode codes.Code
}

func runRevokeTokenCase(t *testing.T, tc revokeTokenCase) {
	t.Helper()

	repo := tc.repo
	if repo == nil {
		repo = &fakeTokenRepo{}
	}
	s := newTestServer(t, &fakeTokenValidator{}, repo, &fakeAgentsStore{})

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
