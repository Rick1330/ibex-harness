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

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: cfg.LogLevel}))
	slog.SetDefault(logger)

	db, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		logger.Error("postgres open failed", "error", err)
		os.Exit(1)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)

	repo := repository.NewTokensRepository(db)
	agentsRepo := repository.NewAgentsRepository(db)
	validator := token.NewValidator(repo, cfg.Argon2)
	tokenSvc := service.NewTokenService(repo, cfg.Argon2, logger)
	meter := metrics.New()

	grpcSrv := grpc.NewServer(
		grpc.UnaryInterceptor(grpcserver.AuthzUnaryInterceptor(validator)),
	)
	authv1.RegisterAuthServiceServer(grpcSrv, grpcserver.NewServer(validator, tokenSvc, agentsRepo, meter))

	grpcLis, err := net.Listen("tcp", config.ListenAddress(cfg.GRPCPort))
	if err != nil {
		logger.Error("grpc listen failed", "error", err)
		os.Exit(1)
	}

	httpServer := &http.Server{
		Addr:              config.ListenAddress(cfg.Port),
		Handler:           authhttp.NewRouter(cfg, logger, meter),
		ReadHeaderTimeout: 5 * time.Second,
	}

	runWithShutdown(cfg, logger, grpcSrv, grpcLis, httpServer, db)
}

func runWithShutdown(
	cfg config.Config,
	logger *slog.Logger,
	grpcSrv *grpc.Server,
	grpcLis net.Listener,
	httpServer *http.Server,
	db *sql.DB,
) {
	errCh := make(chan error, 2)
	go func() {
		logger.Info("grpc starting", "port", cfg.GRPCPort)
		if err := grpcSrv.Serve(grpcLis); err != nil {
			errCh <- err
			return
		}
		errCh <- nil
	}()
	go func() {
		logger.Info("http starting", "service", cfg.ServiceName, "port", cfg.Port, "env", cfg.Environment)
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	sd := shutdown.New(cfg.ShutdownTimeout, logger)
	sd.Register(func(ctx context.Context) error {
		return shutdown.GracefulStopGRPC(grpcSrv, ctx)
	})
	sd.Register(func(ctx context.Context) error {
		return httpServer.Shutdown(ctx)
	})
	sd.Register(func(ctx context.Context) error {
		return db.Close()
	})

	shutdownErrCh := make(chan error, 1)
	go func() {
		shutdownErrCh <- sd.Wait()
	}()

	select {
	case err := <-errCh:
		if err != nil {
			logger.Error("server failed", "error", err)
			os.Exit(1)
		}
	case err := <-shutdownErrCh:
		if err != nil {
			os.Exit(1)
		}
		logger.Info("service stopped", "service", cfg.ServiceName)
	}
}
