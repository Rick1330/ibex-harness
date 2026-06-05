//go:build integration

package integrationtest

import (
	"net"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// AuthGRPCFixture runs an in-process auth gRPC server for integration tests.
type AuthGRPCFixture struct {
	Addr    string
	Client  authv1.AuthServiceClient
	cleanup func()
}

// StartAuthGRPC starts AuthService on an ephemeral port backed by dbDSN.
func StartAuthGRPC(t testing.TB, dbDSN string) *AuthGRPCFixture {
	t.Helper()
	db := testutil.OpenDB(t, dbDSN)
	repo := repository.NewTokensRepository(db)
	agentsRepo := repository.NewAgentsRepository(db)
	argon2 := token.DefaultArgon2Params()
	validator := token.NewValidator(repo, argon2)
	tokenSvc := service.NewTokenService(repo, argon2, nil)
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
	return &AuthGRPCFixture{
		Addr:   lis.Addr().String(),
		Client: authv1.NewAuthServiceClient(conn),
		cleanup: func() {
			grpcSrv.GracefulStop()
			_ = conn.Close()
			_ = db.Close()
		},
	}
}

// Close stops the auth gRPC server and closes resources.
func (f *AuthGRPCFixture) Close() {
	if f.cleanup != nil {
		f.cleanup()
	}
}
