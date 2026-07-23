package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
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
	"google.golang.org/grpc"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	return runBootstrap(args, nil)
}

func runBootstrap(_ []string, signalCh chan os.Signal) int {
	cfg, err := config.Load()
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("invalid configuration", "error", err)
		return 1
	}

	log, err := logger.New(logger.Config{Service: cfg.ServiceName, Level: cfg.LogLevel})
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("logger init failed", "error", err)
		return 1
	}

	db, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		log.ErrorCtx(context.Background(), "postgres open failed", "error", err)
		return 1
	}
	configurePostgresPool(db)

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: cfg.ServiceName, DB: db})
	repo := repository.NewTokensRepository(db, reg)
	agentsRepo := repository.NewAgentsRepository(db, reg)
	validator := token.NewValidator(repo, cfg.Argon2)

	redisClient, publisher, err := setupRevocationPublisher(cfg, log, reg)
	if err != nil {
		log.ErrorCtx(context.Background(), "revocation publisher setup failed", "error", err)
		return 1
	}
	tokenSvc := service.NewTokenService(repo, cfg.Argon2, log, publisher)

	providers, tracer, err := telemetry.InitTracer(context.Background(), cfg.Telemetry, "ibex-auth")
	if err != nil {
		log.ErrorCtx(context.Background(), "telemetry init failed", "error", err)
		return 1
	}

	grpcSrv := grpc.NewServer(
		grpc.ChainUnaryInterceptor(
			grpcserver.MetricsUnaryInterceptor(reg),
			grpcserver.AuthzUnaryInterceptor(validator),
		),
	)
	authv1.RegisterAuthServiceServer(grpcSrv, grpcserver.NewServer(validator, tokenSvc, agentsRepo, reg))

	grpcLis, err := net.Listen("tcp", config.ListenAddress(cfg.GRPCPort))
	if err != nil {
		log.ErrorCtx(context.Background(), "grpc listen failed", "error", err)
		return 1
	}

	healthSrv := &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"postgres": healthcheck.PostgresSelect1(db),
			"grpc":     healthcheck.TCPReachable(config.ListenAddress(cfg.GRPCPort)),
		},
	}

	httpServer := &http.Server{
		Addr:              config.ListenAddress(cfg.Port),
		Handler:           authhttp.NewRouter(log, reg, tracer, healthSrv),
		ReadHeaderTimeout: 5 * time.Second,
	}

	return runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, providers: providers, grpcSrv: grpcSrv, grpcLis: grpcLis,
		httpServer: httpServer, db: db, redisClient: redisClient, signalCh: signalCh,
	})
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
