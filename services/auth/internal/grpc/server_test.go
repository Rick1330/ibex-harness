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
	"google.golang.org/grpc/status"
)

func TestServer_ValidateToken(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		fn       func(context.Context, string) (*authv1.ValidateTokenResponse, error)
		wantCode codes.Code
	}{
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
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			s := newTestServer(t, &fakeTokenValidator{fn: tc.fn}, &fakeTokenRepo{}, &fakeAgentsStore{})

			resp, err := s.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{AccessToken: "tok"})

			if tc.wantCode == codes.OK {
				if err != nil {
					t.Fatalf("ValidateToken: %v", err)
				}
				if resp.GetOrgId() != "org-1" || resp.GetPermissions() != 7 {
					t.Fatalf("response: %+v", resp)
				}
				return
			}
			if status.Code(err) != tc.wantCode {
				t.Fatalf("code: got %v want %v", status.Code(err), tc.wantCode)
			}
		})
	}
}

func TestServer_CreateToken(t *testing.T) {
	t.Parallel()

	orgID := uuid.NewString()

	tests := []struct {
		name     string
		ctx      context.Context
		req      *authv1.CreateTokenRequest
		wantCode codes.Code
	}{
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
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			s := newTestServer(t,
				&fakeTokenValidator{},
				&fakeTokenRepo{},
				&fakeAgentsStore{},
			)

			resp, err := s.CreateToken(tc.ctx, tc.req)

			if tc.wantCode == codes.OK {
				if err != nil {
					t.Fatalf("CreateToken: %v", err)
				}
				if resp.GetTokenId() == "" || resp.GetPlaintext() == "" {
					t.Fatalf("incomplete response: %+v", resp)
				}
				return
			}
			if status.Code(err) != tc.wantCode {
				t.Fatalf("code: got %v want %v err=%v", status.Code(err), tc.wantCode, err)
			}
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
