package main

import (
	"context"
	"database/sql"
	"net"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
)

func TestBootstrapResources_cleanupNoPanic(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	providers, _, err := telemetry.InitTracer(context.Background(), telemetry.Config{ServiceName: "auth-cleanup"}, "ibex-auth")
	if err != nil {
		t.Fatal(err)
	}
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}

	res := &bootstrapResources{
		db:        db,
		providers: providers,
		grpcLis:   lis,
	}
	res.cleanup()
}

func TestInitAuthRuntime_telemetryFailureCleansUp(t *testing.T) {
	cfg := config.Config{
		Environment: "development",
		ServiceName: "auth",
		PostgresDSN: "postgres://ibex:ibex@127.0.0.1:5432/ibex?sslmode=disable",
		Telemetry:   telemetry.Config{},
	}
	log := logger.Discard("auth")
	res := &bootstrapResources{}
	defer res.cleanup()

	_, err := initAuthRuntime(cfg, log, res)
	if err == nil {
		t.Fatal("expected telemetry init failure")
	}
	if res.db == nil {
		t.Fatal("expected postgres handle before telemetry failure")
	}
}

func TestNewAuthHTTPServer_buildsServer(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
	srv := newAuthHTTPServer(authHTTPServerOpts{
		Config: config.Config{Port: "0", GRPCPort: "0"},
		Log:    logger.Discard("auth"),
		Reg:    reg,
		Tracer: telemetry.NoopTracer("auth"),
		DB:     db,
	})
	if srv == nil || srv.Handler == nil {
		t.Fatal("expected configured http server")
	}
}

func TestStartAuthGRPC_portInUse(t *testing.T) {
	ln, err := net.Listen("tcp", config.ListenAddress("0"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = ln.Close() })
	_, port, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
	repo := repository.NewTokensRepository(db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	validator := token.NewValidator(repo, token.DefaultArgon2Params())
	tokenSvc := service.NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), nil)
	deps := authServiceDeps{validator: validator, tokenSvc: tokenSvc, agentsRepo: agentsRepo}

	_, _, err = startAuthGRPC(config.Config{GRPCPort: port}, deps, reg)
	if err == nil {
		t.Fatal("expected listen error when grpc port is in use")
	}
}

func TestSetupRevocationPublisher_emptyRedisURL(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
	log := logger.Discard("auth")

	client, pub, err := setupRevocationPublisher(config.Config{RedisURL: ""}, log, reg)
	if err != nil {
		t.Fatalf("setupRevocationPublisher: %v", err)
	}
	if client != nil {
		t.Fatal("expected nil redis client when REDIS_URL empty")
	}
	if pub == nil {
		t.Fatal("expected noop publisher")
	}
}

func TestSetupRevocationPublisher_invalidRedisURL(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
	log := logger.Discard("auth")

	_, _, err = setupRevocationPublisher(config.Config{RedisURL: "not-a-redis-url"}, log, reg)
	if err == nil {
		t.Fatal("expected redis URL parse error")
	}
}

func TestInitAuthServices_invalidRedisURL(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
	log := logger.Discard("auth")

	_, err = initAuthServices(config.Config{
		RedisURL: "not-a-redis-url",
		Argon2:   token.DefaultArgon2Params(),
	}, db, log, reg)
	if err == nil {
		t.Fatal("expected init failure for invalid redis URL")
	}
}

func TestNewAuthGRPCServer_rejectsInvalidDeps(t *testing.T) {
	t.Parallel()

	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
	repo := repository.NewTokensRepository(db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	validator := token.NewValidator(repo, token.DefaultArgon2Params())
	tokenSvc := service.NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), nil)
	deps := authServiceDeps{validator: validator, tokenSvc: tokenSvc, agentsRepo: agentsRepo}

	_, err = newAuthGRPCServer(deps, nil)
	if err == nil {
		t.Fatal("expected grpc server construction error")
	}
}
