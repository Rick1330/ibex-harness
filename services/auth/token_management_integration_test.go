//go:build integration

package auth_test

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func startAuthGRPC(t *testing.T, dbDSN string) (authv1.AuthServiceClient, func()) {
	t.Helper()
	db := testutil.OpenDB(t, dbDSN)
	repo := repository.NewTokensRepository(db)
	agentsRepo := repository.NewAgentsRepository(db)
	argon2 := token.DefaultArgon2Params()
	validator := token.NewValidator(repo, argon2)
	tokenSvc := service.NewTokenService(repo, argon2, logger.Discard("auth"))
	meter := metrics.New()

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	grpcSrv := grpc.NewServer(grpc.UnaryInterceptor(grpcserver.AuthzUnaryInterceptor(validator)))
	authv1.RegisterAuthServiceServer(grpcSrv, grpcserver.NewServer(validator, tokenSvc, agentsRepo, meter))
	go func() { _ = grpcSrv.Serve(lis) }()

	conn, err := grpc.NewClient(lis.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	return authv1.NewAuthServiceClient(conn), func() {
		grpcSrv.GracefulStop()
		_ = conn.Close()
		_ = db.Close()
	}
}

func authCtx(bearer string) context.Context {
	md := metadata.Pairs("authorization", "Bearer "+bearer)
	return metadata.NewOutgoingContext(context.Background(), md)
}

func TestTokenManagementCreateValidateRevoke(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	orgID := testutil.SeedOrganization(t, db, "Mgmt Org", "mgmt-"+uuid.NewString()[:8])
	adminBearer := testutil.SeedBootstrapAdminToken(t, db, orgID)
	_ = db.Close()

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	ctx := authCtx(adminBearer)
	createResp, err := client.CreateToken(ctx, &authv1.CreateTokenRequest{
		OrgId:       orgID,
		Name:        "ci-pat",
		Type:        authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	plaintext := createResp.GetPlaintext()
	if plaintext == "" || createResp.GetPrefix() == "" {
		t.Fatal("expected plaintext and prefix")
	}

	valCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	valResp, err := client.ValidateToken(valCtx, &authv1.ValidateTokenRequest{AccessToken: plaintext})
	if err != nil {
		t.Fatalf("validate created: %v", err)
	}
	if valResp.GetOrgId() != orgID {
		t.Fatalf("org: %s", valResp.GetOrgId())
	}

	_, err = client.RevokeToken(authCtx(adminBearer), &authv1.RevokeTokenRequest{
		OrgId:   orgID,
		TokenId: createResp.GetTokenId(),
	})
	if err != nil {
		t.Fatalf("revoke: %v", err)
	}

	_, err = client.ValidateToken(context.Background(), &authv1.ValidateTokenRequest{AccessToken: plaintext})
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("revoked validate: %v", err)
	}
}

func TestListTokensAfterCreate(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	orgID := testutil.SeedOrganization(t, db, "List Org", "list-"+uuid.NewString()[:8])
	adminBearer := testutil.SeedBootstrapAdminToken(t, db, orgID)
	_ = db.Close()

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	ctx := authCtx(adminBearer)
	_, tokenID1 := testutil.SeedTokenViaCreateToken(t, client, adminBearer, orgID, permissions.AgentDefault)
	_, tokenID2 := testutil.SeedTokenViaCreateToken(t, client, adminBearer, orgID, permissions.ReadOnly)

	listResp, err := client.ListTokens(ctx, &authv1.ListTokensRequest{
		OrgId: orgID,
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(listResp.GetTokens()) < 2 {
		t.Fatalf("expected at least 2 tokens, got %d", len(listResp.GetTokens()))
	}
	seen := map[string]bool{}
	for _, meta := range listResp.GetTokens() {
		if meta.GetPrefix() == "" || meta.GetTokenId() == "" {
			t.Fatal("metadata missing id or prefix")
		}
		seen[meta.GetTokenId()] = true
	}
	if !seen[tokenID1] || !seen[tokenID2] {
		t.Fatalf("list missing created ids: %v", seen)
	}
}

func TestRevokeTokenCrossTenant(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	orgA := testutil.SeedOrganization(t, db, "Org A", "xa-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "xb-"+uuid.NewString()[:8])
	adminA := testutil.SeedBootstrapAdminToken(t, db, orgA)

	tokenIDB := uuid.New()
	bearerB := "ibex_pat_" + tokenIDB.String() + "_orgbsecret"
	hash, err := token.HashForTest(bearerB, token.DefaultArgon2Params())
	if err != nil {
		t.Fatalf("hash: %v", err)
	}
	repo := repository.NewTokensRepository(db)
	idB, err := repo.InsertTestToken(context.Background(), orgB, "ibex_pat_"+tokenIDB.String(), hash, "b", 1, false, nil)
	if err != nil {
		t.Fatalf("insert b: %v", err)
	}
	_ = db.Close()

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	_, err = client.RevokeToken(authCtx(adminA), &authv1.RevokeTokenRequest{
		OrgId:   orgB,
		TokenId: idB,
	})
	if status.Code(err) != codes.NotFound {
		t.Fatalf("cross-tenant revoke: code=%v err=%v", status.Code(err), err)
	}
}
