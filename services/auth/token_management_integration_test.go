//go:build integration

package auth_test

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func startAuthGRPC(t *testing.T, dbDSN string) (authv1.AuthServiceClient, func()) {
	t.Helper()
	db := testutil.OpenDB(t, dbDSN)
	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth-test", DB: db})
	repo := repository.RequireTokensRepository(t, db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	argon2 := token.TestArgon2Params()
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	validator, err := token.NewValidator(lookup, argon2)
	if err != nil {
		t.Fatalf("NewValidator: %v", err)
	}
	subjects, err := service.NewRepoTokenSubjects(agentsRepo, service.UsersFinder(repository.NewUsersRepository(db, reg)))
	if err != nil {
		t.Fatalf("NewRepoTokenSubjects: %v", err)
	}
	tokenSvc := service.NewTokenService(repo, argon2, logger.Discard("auth"), nil).WithSubjectLookup(subjects)
	agentSvc, err := service.NewAgentService(agentsRepo)
	require.NoError(t, err)

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	grpcSrv := grpc.NewServer( // nosemgrep: go.grpc.security.grpc-server-insecure-connection
		grpc.ChainUnaryInterceptor(
			grpcserver.MetricsUnaryInterceptor(reg),
			grpcserver.AuthzUnaryInterceptor(validator),
		))
	srv, err := grpcserver.NewServer(grpcserver.ServerDeps{
		Validator: validator, TokenService: tokenSvc, AgentService: agentSvc, Metrics: reg,
		Log: logger.Discard("auth"),
	})
	require.NoError(t, err)
	authv1.RegisterAuthServiceServer(grpcSrv, srv)
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
	repo := repository.RequireTokensRepository(t, db, nil)
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
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("cross-tenant revoke: code=%v err=%v", status.Code(err), err)
	}
}

func TestCreateTokenCrossTenant(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	orgA := testutil.SeedOrganization(t, db, "Org A", "ca-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "cb-"+uuid.NewString()[:8])
	adminA := testutil.SeedBootstrapAdminToken(t, db, orgA)
	_ = db.Close()

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	_, err := client.CreateToken(authCtx(adminA), &authv1.CreateTokenRequest{
		OrgId:       orgB,
		Name:        "cross-tenant",
		Type:        authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("cross-tenant create: code=%v err=%v", status.Code(err), err)
	}
}

func TestCreateTokenPermissionSubset(t *testing.T) {
	dsn, cleanupPG := testutil.SetupPostgres(t)
	defer cleanupPG()

	db := testutil.OpenDB(t, dsn)
	orgID := testutil.SeedOrganization(t, db, "Subset Org", "sub-"+uuid.NewString()[:8])
	limitedBearer, _ := testutil.SeedToken(t, db, orgID, permissions.TokenCreate)
	adminBearer := testutil.SeedBootstrapAdminToken(t, db, orgID)
	_ = db.Close()

	client, cleanup := startAuthGRPC(t, dsn)
	defer cleanup()

	_, err := client.CreateToken(authCtx(limitedBearer), &authv1.CreateTokenRequest{
		OrgId:       orgID,
		Name:        "escalate-admin",
		Type:        authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.Admin,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("escalate create: code=%v err=%v", status.Code(err), err)
	}

	resp, err := client.CreateToken(authCtx(adminBearer), &authv1.CreateTokenRequest{
		OrgId:       orgID,
		Name:        "agent-ok",
		Type:        authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault,
	})
	if err != nil {
		t.Fatalf("admin subset create: %v", err)
	}
	if resp.GetPlaintext() == "" {
		t.Fatal("expected plaintext")
	}

	valCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	val, err := client.ValidateToken(valCtx, &authv1.ValidateTokenRequest{AccessToken: resp.GetPlaintext()})
	if err != nil {
		t.Fatalf("validate minted: %v", err)
	}
	if val.GetPermissions() != permissions.AgentDefault {
		t.Fatalf("minted permissions=%d want AgentDefault", val.GetPermissions())
	}
}

func TestCreateTokenSubjectOrgBind(t *testing.T) {
	t.Parallel()
	fx := seedSubjectBindFixture(t)
	client, cleanup := startAuthGRPC(t, fx.dsn)
	defer cleanup()

	assertCreateDenied(t, client, createDeniedArgs{
		bearer: fx.adminA, orgID: fx.orgA, name: "cross-agent", agentID: &fx.agentB,
	})
	assertCreateDenied(t, client, createDeniedArgs{
		bearer: fx.adminA, orgID: fx.orgA, name: "cross-user", userID: &fx.userB,
	})
	assertSameOrgBindOK(t, client, fx)
}

type subjectBindFixture struct {
	dsn            string
	orgA, adminA   string
	userA, userB   string
	agentA, agentB string
}

func seedSubjectBindFixture(t *testing.T) subjectBindFixture {
	t.Helper()
	dsn, cleanupPG := testutil.SetupPostgres(t)
	t.Cleanup(cleanupPG)

	db := testutil.OpenDB(t, dsn)
	defer func() { _ = db.Close() }()

	orgA := testutil.SeedOrganization(t, db, "Bind Org A", "bind-a-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Bind Org B", "bind-b-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "b-"+uuid.NewString()[:8]+"@example.com", "User B")
	return subjectBindFixture{
		dsn:    dsn,
		orgA:   orgA,
		adminA: testutil.SeedBootstrapAdminToken(t, db, orgA),
		userA:  userA,
		userB:  userB,
		agentA: testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8]),
		agentB: testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8]),
	}
}

type createDeniedArgs struct {
	bearer, orgID, name string
	agentID, userID     *string
}

func assertCreateDenied(t *testing.T, client authv1.AuthServiceClient, a createDeniedArgs) {
	t.Helper()
	_, err := client.CreateToken(authCtx(a.bearer), &authv1.CreateTokenRequest{
		OrgId: a.orgID, Name: a.name, Type: authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault, AgentId: a.agentID, UserId: a.userID,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("%s: code=%v err=%v", a.name, status.Code(err), err)
	}
}

func assertSameOrgBindOK(t *testing.T, client authv1.AuthServiceClient, fx subjectBindFixture) {
	t.Helper()
	resp, err := client.CreateToken(authCtx(fx.adminA), &authv1.CreateTokenRequest{
		OrgId: fx.orgA, Name: "same-org", Type: authv1.TokenType_TOKEN_TYPE_PAT,
		Permissions: permissions.AgentDefault, AgentId: &fx.agentA, UserId: &fx.userA,
	})
	if err != nil {
		t.Fatalf("same-org bind: %v", err)
	}
	valCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	val, err := client.ValidateToken(valCtx, &authv1.ValidateTokenRequest{AccessToken: resp.GetPlaintext()})
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if val.GetAgentId() != fx.agentA {
		t.Fatalf("agent=%q want %q", val.GetAgentId(), fx.agentA)
	}
	if val.GetUserId() != fx.userA {
		t.Fatalf("user=%q want %q", val.GetUserId(), fx.userA)
	}
}
