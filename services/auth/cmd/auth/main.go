package main

import (
	"context"
	"database/sql"
	"fmt"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	authhttp "github.com/Rick1330/ibex-harness/services/auth/internal/http"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	return runBootstrap(args, nil)
}

func runBootstrap(_ []string, signalCh chan os.Signal) int {
	cfg, log, ok := loadAuthBootstrap()
	if !ok {
		return 1
	}

	db, err := openAuthPostgres(cfg)
	if err != nil {
		log.ErrorCtx(context.Background(), "postgres open failed", "error", err)
		return 1
	}

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: cfg.ServiceName, DB: db})
	deps, err := initAuthServices(cfg, db, log, reg)
	if err != nil {
		log.ErrorCtx(context.Background(), "auth services init failed", "error", err)
		return 1
	}

	providers, tracer, ok := initAuthTelemetry(cfg, log)
	if !ok {
		return 1
	}

	grpcSrv, grpcLis, err := startAuthGRPC(cfg, deps, reg)
	if err != nil {
		log.ErrorCtx(context.Background(), "grpc startup failed", "error", err)
		return 1
	}

	httpServer := newAuthHTTPServer(cfg, authHTTPDeps{
		Log: log, Reg: reg, Tracer: tracer, DB: db,
	})

	return runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, providers: providers, grpcSrv: grpcSrv, grpcLis: grpcLis,
		httpServer: httpServer, db: db, redisClient: deps.redisClient, tokenSvc: deps.tokenSvc, signalCh: signalCh,
	})
}

func loadAuthBootstrap() (config.Config, *logger.Logger, bool) {
	cfg, err := config.Load()
	if err != nil {
		logger.BootstrapError("invalid configuration", err)
		return config.Config{}, nil, false
	}
	log, err := logger.New(logger.Config{Service: cfg.ServiceName, Level: cfg.LogLevel})
	if err != nil {
		logger.BootstrapError("logger init failed", err)
		return config.Config{}, nil, false
	}
	return cfg, log, true
}

type authServiceDeps struct {
	validator   *token.Validator
	tokenSvc    *service.TokenService
	agentsRepo  *repository.AgentsRepository
	redisClient redis.UniversalClient
}

func initAuthServices(
	cfg config.Config,
	db *sql.DB,
	log *logger.Logger,
	reg *ibexmetrics.AuthRegistry,
) (authServiceDeps, error) {
	repo := repository.NewTokensRepository(db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	validator := token.NewValidator(repo, cfg.Argon2)

	redisClient, publisher, err := setupRevocationPublisher(cfg, log, reg)
	if err != nil {
		return authServiceDeps{}, err
	}
	tokenSvc := service.NewTokenService(repo, cfg.Argon2, log, publisher)
	return authServiceDeps{
		validator: validator, tokenSvc: tokenSvc, agentsRepo: agentsRepo, redisClient: redisClient,
	}, nil
}

func newAuthGRPCServer(deps authServiceDeps, reg *ibexmetrics.AuthRegistry) (*grpc.Server, error) {
	grpcSrv := grpc.NewServer(
		grpc.ChainUnaryInterceptor(
			grpcserver.MetricsUnaryInterceptor(reg),
			grpcserver.AuthzUnaryInterceptor(deps.validator),
		),
	)
	if err := registerAuthGRPC(grpcSrv, deps, reg); err != nil {
		return nil, err
	}
	return grpcSrv, nil
}

func setupRevocationPublisher(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.AuthRegistry,
) (redis.UniversalClient, revocation.Publisher, error) {
	if cfg.RedisURL == "" {
		log.InfoCtx(context.Background(), "revocation publisher disabled; REDIS_URL empty")
		return nil, revocation.NoopPublisher{}, nil
	}
	client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
	if err != nil {
		return nil, nil, fmt.Errorf("redis client init: %w", err)
	}
	pub, err := revocation.NewRedisPublisher(client, log, reg)
	if err != nil {
		_ = client.Close()
		return nil, nil, err
	}
	log.InfoCtx(context.Background(), "revocation publisher configured", "channel", revocation.Channel)
	return client, pub, nil
}

func configurePostgresPool(db *sql.DB) {
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)
}

func startAuthGRPC(
	cfg config.Config,
	deps authServiceDeps,
	reg *ibexmetrics.AuthRegistry,
) (*grpc.Server, net.Listener, error) {
	grpcSrv, err := newAuthGRPCServer(deps, reg)
	if err != nil {
		return nil, nil, err
	}
	lis, err := net.Listen("tcp", config.ListenAddress(cfg.GRPCPort))
	if err != nil {
		return nil, nil, err
	}
	return grpcSrv, lis, nil
}

func initAuthTelemetry(cfg config.Config, log *logger.Logger) (*telemetry.Providers, trace.Tracer, bool) {
	providers, tracer, err := telemetry.InitTracer(context.Background(), cfg.Telemetry, "ibex-auth")
	if err != nil {
		log.ErrorCtx(context.Background(), "telemetry init failed", "error", err)
		return nil, nil, false
	}
	return providers, tracer, true
}

func openAuthPostgres(cfg config.Config) (*sql.DB, error) {
	db, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		return nil, err
	}
	configurePostgresPool(db)
	return db, nil
}

type authHTTPDeps struct {
	Log    *logger.Logger
	Reg    *ibexmetrics.AuthRegistry
	Tracer trace.Tracer
	DB     *sql.DB
}

func newAuthHTTPServer(cfg config.Config, deps authHTTPDeps) *http.Server {
	healthSrv := &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"postgres": healthcheck.PostgresSelect1(deps.DB),
			"grpc":     healthcheck.TCPReachable(config.ListenAddress(cfg.GRPCPort)),
		},
	}
	return &http.Server{
		Addr:              config.ListenAddress(cfg.Port),
		Handler:           authhttp.NewRouter(deps.Log, deps.Reg, deps.Tracer, healthSrv),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      120 * time.Second,
		IdleTimeout:       90 * time.Second,
	}
}

func registerAuthGRPC(grpcSrv *grpc.Server, deps authServiceDeps, reg *ibexmetrics.AuthRegistry) error {
	srv, err := grpcserver.NewServer(deps.validator, deps.tokenSvc, deps.agentsRepo, reg)
	if err != nil {
		return err
	}
	authv1.RegisterAuthServiceServer(grpcSrv, srv)
	return nil
}
