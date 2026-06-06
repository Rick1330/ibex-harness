package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("invalid configuration", "error", err)
		os.Exit(1)
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: cfg.LogLevel}))
	slog.SetDefault(logger)

	meter := metrics.New()

	var redisClient redis.UniversalClient
	var limiter ratelimit.Limiter = ratelimit.Noop()
	if cfg.RedisURL != "" {
		client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
		if err != nil {
			logger.Error("redis client init failed", "error", err)
			os.Exit(1)
		}
		redisClient = client
		limiter = ratelimit.NewRedisSlider(client, rateLimitSliderConfig(cfg))
		logger.Info("rate limiter configured", "default_rpm", cfg.RateLimit.DefaultRPM, "org_overrides", len(cfg.RateLimit.OrgOverrides))
	}

	var validator auth.TokenValidator
	var grpcConn *grpc.ClientConn
	if cfg.AuthGRPCAddr != "" {
		conn, err := grpc.NewClient(cfg.AuthGRPCAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
		if err != nil {
			logger.Error("auth grpc dial failed", "error", err, "addr", cfg.AuthGRPCAddr)
			os.Exit(1)
		}
		grpcConn = conn
		validator = auth.NewGRPCValidator(authv1.NewAuthServiceClient(conn), cfg.AuthValidateTimeout)
		logger.Info("auth grpc client configured", "addr", cfg.AuthGRPCAddr, "timeout", cfg.AuthValidateTimeout.String())
	}

	server := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           proxyhttp.NewRouter(cfg, logger, meter, validator, limiter),
		ReadHeaderTimeout: 5 * time.Second,
	}

	errCh := make(chan error, 1)
	go func() {
		logger.Info("service starting", "service", cfg.ServiceName, "port", cfg.Port, "env", cfg.Environment)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
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
	if err := server.Shutdown(ctx); err != nil {
		logger.Error("graceful shutdown failed", "error", err)
		os.Exit(1)
	}
	if grpcConn != nil {
		_ = grpcConn.Close()
	}
	if redisClient != nil {
		_ = redisClient.Close()
	}
	logger.Info("service stopped", "service", cfg.ServiceName)
}

func rateLimitSliderConfig(cfg config.Config) ratelimit.RedisSliderConfig {
	overrides := make(map[uuid.UUID]int64, len(cfg.RateLimit.OrgOverrides))
	for orgID, rpm := range cfg.RateLimit.OrgOverrides {
		overrides[orgID] = int64(rpm)
	}
	return ratelimit.RedisSliderConfig{
		DefaultRPM:   int64(cfg.RateLimit.DefaultRPM),
		OrgOverrides: overrides,
	}
}
