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
	"github.com/alicebob/miniredis/v2"
)

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:5432/test?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := db.Close(); err != nil {
			t.Errorf("close db: %v", err)
		}
	})
	return db
}

func assertAuthServiceDeps(t *testing.T, deps authServiceDeps) {
	t.Helper()
	if deps.tokenSvc == nil {
		t.Fatal("expected token service")
	}
	if deps.validator == nil {
		t.Fatal("expected validator")
	}
	if deps.agentsRepo == nil {
		t.Fatal("expected agents repo")
	}
}

func newTestAuthRegistry(t *testing.T, db *sql.DB) *ibexmetrics.AuthRegistry {
	t.Helper()
	return ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth", DB: db})
}

func newTestAuthServiceDeps(t *testing.T, db *sql.DB, reg *ibexmetrics.AuthRegistry) authServiceDeps {
	t.Helper()
	repo := repository.RequireTokensRepository(t, db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	usersRepo := repository.NewUsersRepository(db, reg)
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		t.Fatalf("NewRepoLookup: %v", err)
	}
	validator := token.NewValidator(lookup, token.DefaultArgon2Params())
	subjects := service.NewRepoTokenSubjects(agentsRepo, usersRepo)
	tokenSvc := service.NewTokenService(repo, token.DefaultArgon2Params(), logger.Discard("auth"), nil,
		service.WithSubjectLookup(subjects))
	return authServiceDeps{
		validator: validator, tokenSvc: tokenSvc, agentsRepo: agentsRepo,
		log: logger.Discard("auth"),
	}
}

func TestUnit_BootstrapResources_CleanupNoPanic(t *testing.T) {
	t.Parallel()

	// Open without openTestDB cleanup: ownership transfers to res.cleanup().
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

func TestUnit_InitAuthRuntime_TelemetryFailureCleansUp(t *testing.T) {
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

func TestUnit_NewAuthHTTPServer_BuildsServer(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)

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

func TestUnit_StartAuthGRPC_PortInUse(t *testing.T) {
	ln, err := net.Listen("tcp", config.ListenAddress("0"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = ln.Close() })
	_, port, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	deps := newTestAuthServiceDeps(t, db, reg)

	_, _, err = startAuthGRPC(config.Config{GRPCPort: port}, deps, reg)

	if err == nil {
		t.Fatal("expected listen error when grpc port is in use")
	}
}

func TestUnit_SetupRevocationPublisher_EmptyRedisURL(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
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

func TestUnit_InvalidRedisURL_Rejects(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	log := logger.Discard("auth")
	badURL := "not-a-redis-url"

	cases := []struct {
		name string
		run  func() error
	}{
		{
			name: "revocation publisher",
			run: func() error {
				_, _, err := setupRevocationPublisher(config.Config{RedisURL: badURL}, log, reg)
				return err
			},
		},
		{
			name: "auth services",
			run: func() error {
				_, err := initAuthServices(config.Config{
					RedisURL: badURL,
					Argon2:   token.DefaultArgon2Params(),
				}, db, log, reg)
				return err
			},
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if err := tc.run(); err == nil {
				t.Fatal("expected redis URL parse error")
			}
		})
	}
}

func TestUnit_NewAuthGRPCServer_RejectsInvalidDeps(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	deps := newTestAuthServiceDeps(t, db, reg)

	_, err := newAuthGRPCServer(deps, nil)

	if err == nil {
		t.Fatal("expected grpc server construction error")
	}
}

func TestUnit_InitAuthServices_EmptyRedisURL(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	log := logger.Discard("auth")

	deps, err := initAuthServices(config.Config{
		RedisURL: "",
		Argon2:   token.DefaultArgon2Params(),
	}, db, log, reg)

	if err != nil {
		t.Fatalf("initAuthServices: %v", err)
	}
	assertAuthServiceDeps(t, deps)
	if deps.redisClient != nil {
		t.Fatal("expected nil redis when REDIS_URL empty")
	}
}

func TestUnit_SetupRevocationPublisher_WithMiniredis(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	log := logger.Discard("auth")
	mr := miniredis.RunT(t)

	client, pub, err := setupRevocationPublisher(config.Config{
		RedisURL: "redis://" + mr.Addr() + "/0",
	}, log, reg)

	if err != nil {
		t.Fatalf("setupRevocationPublisher: %v", err)
	}
	t.Cleanup(func() {
		if client == nil {
			return
		}
		if err := client.Close(); err != nil {
			t.Errorf("close redis client: %v", err)
		}
	})
	if client == nil {
		t.Fatal("expected redis client")
	}
	if pub == nil {
		t.Fatal("expected publisher")
	}
}

func TestUnit_NewAuthGRPCServer_BuildsServer(t *testing.T) {
	t.Parallel()

	db := openTestDB(t)
	reg := newTestAuthRegistry(t, db)
	deps := newTestAuthServiceDeps(t, db, reg)

	srv, err := newAuthGRPCServer(deps, reg)

	if err != nil {
		t.Fatalf("newAuthGRPCServer: %v", err)
	}
	if srv == nil {
		t.Fatal("expected grpc server")
	}
	srv.Stop()
}

func TestUnit_InitAuthServices_NilDB(t *testing.T) {
	t.Parallel()

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: "auth"})
	_, err := initAuthServices(config.Config{
		RedisURL: "",
		Argon2:   token.DefaultArgon2Params(),
	}, nil, logger.Discard("auth"), reg)
	if err == nil {
		t.Fatal("expected nil db error from NewTokensRepository")
	}
}

func TestUnit_OpenAuthPostgres_OpensHandle(t *testing.T) {
	t.Parallel()

	db, err := openAuthPostgres(config.Config{
		PostgresDSN: "postgres://127.0.0.1:5432/test?sslmode=disable",
	})
	if err != nil {
		t.Fatalf("openAuthPostgres: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	if db == nil {
		t.Fatal("expected db handle")
	}
}

func TestUnit_ConfigurePostgresPool_NoPanic(t *testing.T) {
	t.Parallel()
	db := openTestDB(t)
	configurePostgresPool(db)
}
