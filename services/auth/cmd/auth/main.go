package main

import (
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
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
	defer func() { _ = db.Close() }()
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)

	repo := repository.NewTokensRepository(db)
	validator := token.NewValidator(repo, cfg.Argon2)
	tokenSvc := service.NewTokenService(repo, cfg.Argon2, logger)
	meter := metrics.New()

	grpcSrv := grpc.NewServer(
		grpc.UnaryInterceptor(grpcserver.AuthzUnaryInterceptor(validator)),
	)
	authv1.RegisterAuthServiceServer(grpcSrv, grpcserver.NewServer(validator, tokenSvc, meter))

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

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-stop:
		logger.Info("shutdown signal received", "signal", sig.String())
	case err := <-errCh:
		if err != nil {
			logger.Error("server failed", "error", err)
			os.Exit(1)
		}
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	grpcSrv.GracefulStop()
	if err := httpServer.Shutdown(ctx); err != nil {
		logger.Error("http shutdown failed", "error", err)
		os.Exit(1)
	}
	logger.Info("service stopped", "service", cfg.ServiceName)
}
