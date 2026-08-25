package grpcserver

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
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

type fakeTokenAPI struct {
	createFn func(context.Context, service.CreateTokenInput) (service.CreateTokenResult, error)
	revokeFn func(context.Context, service.RevokeTokenParams) error
	listFn   func(context.Context, string, string, int32) ([]service.TokenListItem, string, error)
}

func (f *fakeTokenAPI) CreateToken(ctx context.Context, in service.CreateTokenInput) (service.CreateTokenResult, error) {
	if f.createFn != nil {
		return f.createFn(ctx, in)
	}
	if in.OrgID == "" || in.Name == "" {
		return service.CreateTokenResult{}, service.ErrInvalidArgument
	}
	return service.CreateTokenResult{
		TokenID: uuid.NewString(), Plaintext: "ibex_pat_test", Prefix: "ibex_pat_",
		CreatedAt: time.Now().UTC(),
	}, nil
}

func (f *fakeTokenAPI) RevokeToken(ctx context.Context, p service.RevokeTokenParams) error {
	if f.revokeFn != nil {
		return f.revokeFn(ctx, p)
	}
	return nil
}

func (f *fakeTokenAPI) ListTokens(ctx context.Context, orgID, cursor string, limit int32) ([]service.TokenListItem, string, error) {
	if f.listFn != nil {
		return f.listFn(ctx, orgID, cursor, limit)
	}
	return nil, "", nil
}

type fakeAgentAPI struct {
	view service.AgentView
	err  error
}

func (f *fakeAgentAPI) ValidateForOrg(ctx context.Context, orgID, agentID uuid.UUID) (service.AgentView, error) {
	_ = ctx
	_ = orgID
	_ = agentID
	if f.err != nil {
		return service.AgentView{}, f.err
	}
	if f.view.ID == "" {
		return service.AgentView{}, service.ErrAgentNotAuthorized
	}
	return f.view, nil
}

func testAuthRegistry() *metrics.AuthRegistry {
	return metrics.NewAuth(metrics.AuthConfig{ServiceName: "test"})
}

func newTestServer(t testing.TB, validator tokenValidator, tokens tokenAPI, agents validateForOrger) *Server {
	t.Helper()
	if tokens == nil {
		tokens = &fakeTokenAPI{}
	}
	if agents == nil {
		agents = &fakeAgentAPI{}
	}
	srv, err := NewServer(ServerDeps{
		Validator: validator, TokenService: tokens, AgentService: agents,
		Metrics: testAuthRegistry(), Log: logger.Discard("auth"),
	})
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

func assertOKOrGRPCCode(t *testing.T, err error, want codes.Code, onOK func()) {
	t.Helper()
	if want == codes.OK {
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		onOK()
		return
	}
	assertGRPCCode(t, err, want)
}
