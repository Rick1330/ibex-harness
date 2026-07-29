package grpcserver

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type fakeTokenValidator struct {
	fn func(context.Context, string) (*authv1.ValidateTokenResponse, error)
}

func (f *fakeTokenValidator) Validate(ctx context.Context, accessToken string) (*authv1.ValidateTokenResponse, error) {
	return f.fn(ctx, accessToken)
}

type fakeTokenRepo struct {
	createFn func(context.Context, repository.CreateTokenParams) (string, error)
	revokeFn func(context.Context, repository.RevokeTokenInput) error
	listFn   func(context.Context, string, string, int) ([]repository.TokenMetadata, string, error)
}

func (f *fakeTokenRepo) CreateToken(ctx context.Context, p repository.CreateTokenParams) (string, error) {
	if f.createFn != nil {
		return f.createFn(ctx, p)
	}
	return p.ID, nil
}

func (f *fakeTokenRepo) RevokeToken(ctx context.Context, in repository.RevokeTokenInput) error {
	if f.revokeFn != nil {
		return f.revokeFn(ctx, in)
	}
	return nil
}

func (f *fakeTokenRepo) ListTokens(ctx context.Context, orgID, cursor string, limit int) ([]repository.TokenMetadata, string, error) {
	if f.listFn != nil {
		return f.listFn(ctx, orgID, cursor, limit)
	}
	return nil, "", nil
}

type serviceTokenRepo interface {
	CreateToken(ctx context.Context, p repository.CreateTokenParams) (string, error)
	RevokeToken(ctx context.Context, in repository.RevokeTokenInput) error
	ListTokens(ctx context.Context, orgID, cursor string, limit int) ([]repository.TokenMetadata, string, error)
}

func newTestServer(t testing.TB, validator tokenValidator, tokenRepo serviceTokenRepo, agents AgentStore) *Server {
	t.Helper()
	tokenSvc := service.NewTokenService(tokenRepo, token.DefaultArgon2Params(), logger.Discard("auth"), nil)
	srv, err := NewServer(validator, tokenSvc, agents, testAuthRegistry())
	if err != nil {
		t.Fatalf("NewServer: %v", err)
	}
	return srv
}

func adminCtx(t *testing.T, orgID string) context.Context {
	t.Helper()
	return ContextWithCaller(context.Background(), CallerContext{
		OrgID: orgID, TokenID: uuid.NewString(), UserID: uuid.NewString(), Permissions: permissions.Admin,
	})
}

func revokeTokenRequest(orgID, tokenID string) *authv1.RevokeTokenRequest {
	return &authv1.RevokeTokenRequest{OrgId: orgID, TokenId: tokenID}
}

func assertGRPCCode(t *testing.T, err error, want codes.Code) {
	t.Helper()
	if status.Code(err) != want {
		t.Fatalf("code: got %v want %v err=%v", status.Code(err), want, err)
	}
}
