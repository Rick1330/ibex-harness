//go:build integration

package integrationtest

import (
	"net"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// AuthGRPCFixture runs an in-process auth gRPC server for integration tests.
type AuthGRPCFixture struct {
	Addr     string
	Client   authv1.AuthServiceClient
	tokenSvc *service.TokenService
	cleanup  func()
}

// StartAuthGRPC starts AuthService on an ephemeral port backed by dbDSN.
func StartAuthGRPC(t testing.TB, dbDSN string) *AuthGRPCFixture {
	t.Helper()
	return startAuthGRPC(t, dbDSN, nil)
}

// StartAuthGRPCWithRedis starts AuthService and PUBLISHes revocation events
// on redisClient (shared with a proxy revocation subscriber in SEC tests).
func StartAuthGRPCWithRedis(t testing.TB, dbDSN string, redisClient redis.UniversalClient) *AuthGRPCFixture {
	t.Helper()
	if redisClient == nil {
		t.Fatal("redisClient is required")
	}
	return startAuthGRPC(t, dbDSN, redisClient)
}

func startAuthGRPC(t testing.TB, dbDSN string, redisClient redis.UniversalClient) *AuthGRPCFixture {
	t.Helper()
	db := testutil.OpenDB(t, dbDSN)
	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth-test", DB: db})
	repo := repository.RequireTokensRepository(t, db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	argon2 := token.DefaultArgon2Params()
	validator := mustTokenValidator(t, repo, argon2)
	publisher := revocationPublisher(t, redisClient)
	tokenSvc := mustTokenService(t, tokenServiceParts{
		repo: repo, agents: agentsRepo, users: repository.NewUsersRepository(db, reg),
		argon2: argon2, publisher: publisher,
	})
	agentSvc := mustAgentService(t, agentsRepo)

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
	if err != nil {
		t.Fatalf("grpc server init: %v", err)
	}
	authv1.RegisterAuthServiceServer(grpcSrv, srv)
	go func() { _ = grpcSrv.Serve(lis) }()

	conn, err := grpc.NewClient(lis.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	return &AuthGRPCFixture{
		Addr:     lis.Addr().String(),
		Client:   authv1.NewAuthServiceClient(conn),
		tokenSvc: tokenSvc,
		cleanup: func() {
			tokenSvc.DrainPublishes()
			grpcSrv.GracefulStop()
			_ = conn.Close()
			_ = db.Close()
		},
	}
}

func mustTokenValidator(t testing.TB, repo *repository.TokensRepository, argon2 token.Argon2Params) *token.Validator {
	t.Helper()
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	return token.NewValidator(lookup, argon2)
}

func revocationPublisher(t testing.TB, redisClient redis.UniversalClient) revocation.Publisher {
	t.Helper()
	if redisClient == nil {
		return revocation.NoopPublisher{}
	}
	pub, err := revocation.NewRedisPublisher(redisClient, logger.Discard("auth"), nil)
	if err != nil {
		t.Fatalf("revocation publisher: %v", err)
	}
	return pub
}

type tokenServiceParts struct {
	repo      *repository.TokensRepository
	agents    *repository.AgentsRepository
	users     *repository.UsersRepository
	argon2    token.Argon2Params
	publisher revocation.Publisher
}

func mustTokenService(t testing.TB, p tokenServiceParts) *service.TokenService {
	t.Helper()
	subjects, err := service.NewRepoTokenSubjects(p.agents, service.UsersFinder(p.users))
	if err != nil {
		t.Fatalf("NewRepoTokenSubjects: %v", err)
	}
	return service.NewTokenService(p.repo, p.argon2, logger.Discard("auth"), p.publisher).
		WithSubjectLookup(subjects)
}

func mustAgentService(t testing.TB, agents *repository.AgentsRepository) *service.AgentService {
	t.Helper()
	agentSvc, err := service.NewAgentService(agents)
	if err != nil {
		t.Fatalf("agent service: %v", err)
	}
	return agentSvc
}

// WaitPendingPublishes blocks until in-flight revocation PUBLISH calls finish.
func (f *AuthGRPCFixture) WaitPendingPublishes() {
	if f != nil && f.tokenSvc != nil {
		f.tokenSvc.WaitPendingPublishes()
	}
}

// Close stops the auth gRPC server and closes resources.
func (f *AuthGRPCFixture) Close() {
	if f.cleanup != nil {
		f.cleanup()
	}
}
