package main

import (
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	authhttp "github.com/Rick1330/ibex-harness/services/auth/internal/http"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	_ "github.com/lib/pq"
	"google.golang.org/grpc"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("invalid configuration", "error", err)
		os.Exit(1)
	}

	log, err := logger.New(logger.Config{Service: cfg.ServiceName, Level: cfg.LogLevel})
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("logger init failed", "error", err)
		os.Exit(1)
	}

	db, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		log.ErrorCtx(context.Background(), "postgres open failed", "error", err)
		os.Exit(1)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)

	repo := repository.NewTokensRepository(db)
	agentsRepo := repository.NewAgentsRepository(db)
	validator := token.NewValidator(repo, cfg.Argon2)
	tokenSvc := service.NewTokenService(repo, cfg.Argon2, log)
	meter := metrics.New()

	grpcSrv := grpc.NewServer(
		grpc.UnaryInterceptor(grpcserver.AuthzUnaryInterceptor(validator)),
	)
	authv1.RegisterAuthServiceServer(grpcSrv, grpcserver.NewServer(validator, tokenSvc, agentsRepo, meter))

	grpcLis, err := net.Listen("tcp", config.ListenAddress(cfg.GRPCPort))
	if err != nil {
		log.ErrorCtx(context.Background(), "grpc listen failed", "error", err)
		os.Exit(1)
	}

	httpServer := &http.Server{
		Addr:              config.ListenAddress(cfg.Port),
		Handler:           authhttp.NewRouter(cfg, log, meter),
		ReadHeaderTimeout: 5 * time.Second,
	}

	runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, grpcSrv: grpcSrv, grpcLis: grpcLis,
		httpServer: httpServer, db: db,
	})
}

type shutdownOpts struct {
	cfg        config.Config
	logger     *logger.Logger
	grpcSrv    *grpc.Server
	grpcLis    net.Listener
	httpServer *http.Server
	db         *sql.DB
}

func runWithShutdown(opts shutdownOpts) {
	errCh := make(chan error, 2)
	go func() {
		opts.logger.InfoCtx(context.Background(), "grpc starting", "port", opts.cfg.GRPCPort)
		if err := opts.grpcSrv.Serve(opts.grpcLis); err != nil {
			errCh <- err
			return
		}
		errCh <- nil
	}()
	go func() {
		opts.logger.InfoCtx(context.Background(), "http starting", "port", opts.cfg.Port, "env", opts.cfg.Environment)
		if err := opts.httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	sd := shutdown.New(opts.cfg.ShutdownTimeout, opts.logger)
	sd.Register(func(ctx context.Context) error {
		return shutdown.GracefulStopGRPC(opts.grpcSrv, ctx)
	})
	sd.Register(func(ctx context.Context) error {
		return opts.httpServer.Shutdown(ctx)
	})
	sd.Register(func(ctx context.Context) error {
		return opts.db.Close()
	})

	shutdownErrCh := make(chan error, 1)
	go func() {
		shutdownErrCh <- sd.Wait()
	}()

	select {
	case err := <-errCh:
		if err != nil {
			opts.logger.ErrorCtx(context.Background(), "server failed", "error", err)
			os.Exit(1)
		}
	case err := <-shutdownErrCh:
		if err != nil {
			os.Exit(1)
		}
		opts.logger.InfoCtx(context.Background(), "service stopped")
	}
}
