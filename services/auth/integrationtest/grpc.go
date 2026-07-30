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
	repo := repository.NewTokensRepository(db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	argon2 := token.DefaultArgon2Params()
	validator := token.NewValidator(repo, argon2)

	publisher := revocation.Publisher(revocation.NoopPublisher{})
	if redisClient != nil {
		pub, err := revocation.NewRedisPublisher(redisClient, logger.Discard("auth"), nil)
		if err != nil {
			t.Fatalf("revocation publisher: %v", err)
		}
		publisher = pub
	}
	tokenSvc := service.NewTokenService(repo, argon2, logger.Discard("auth"), publisher)

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
		Validator: validator, TokenService: tokenSvc, AgentsStore: agentsRepo, Metrics: reg,
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
