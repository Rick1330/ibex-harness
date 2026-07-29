package grpcserver

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
)

type listTokensCase struct {
	name     string
	ctx      context.Context
	repo     *fakeTokenRepo
	wantCode codes.Code
	wantLen  int
}

func listTokensCases(t *testing.T, orgID string) []listTokensCase {
	t.Helper()
	created := time.Now().UTC()
	return []listTokensCase{
		{name: "unauthenticated", ctx: context.Background(), wantCode: codes.Unauthenticated},
		{
			name: "permission denied",
			ctx: ContextWithCaller(context.Background(), CallerContext{
				OrgID: uuid.NewString(), Permissions: permissions.Admin,
			}),
			wantCode: codes.PermissionDenied,
		},
		{
			name: "internal error", ctx: adminCtx(t, orgID),
			repo: &fakeTokenRepo{
				listFn: func(context.Context, string, string, int) ([]repository.TokenMetadata, string, error) {
					return nil, "", errors.New("db down")
				},
			},
			wantCode: codes.Internal,
		},
		{
			name: "ok", ctx: adminCtx(t, orgID),
			repo: &fakeTokenRepo{
				listFn: func(context.Context, string, string, int) ([]repository.TokenMetadata, string, error) {
					return []repository.TokenMetadata{
						{ID: "t1", Name: "a", Prefix: "p1", Permissions: 1, CreatedAt: created},
					}, "next-cursor", nil
				},
			},
			wantCode: codes.OK, wantLen: 1,
		},
	}
}

func runListTokensCase(t *testing.T, orgID string, tc listTokensCase) {
	t.Helper()
	repo := tc.repo
	if repo == nil {
		repo = &fakeTokenRepo{}
	}
	s := newTestServer(t, &fakeTokenValidator{}, repo, &fakeAgentsStore{})
	resp, err := s.ListTokens(tc.ctx, &authv1.ListTokensRequest{OrgId: orgID, Limit: 10})
	if tc.wantCode == codes.OK {
		if err != nil {
			t.Fatalf("ListTokens: %v", err)
		}
		if len(resp.GetTokens()) != tc.wantLen {
			t.Fatalf("tokens len: got %d want %d", len(resp.GetTokens()), tc.wantLen)
		}
		if tc.wantLen > 0 && resp.GetNextCursor() != "next-cursor" {
			t.Fatalf("next cursor: %q", resp.GetNextCursor())
		}
		return
	}
	assertGRPCCode(t, err, tc.wantCode)
}
