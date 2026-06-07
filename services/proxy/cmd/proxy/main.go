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
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
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
	redisClient, limiter := setupRateLimiter(cfg, logger)
	validator, agentVerifier, grpcConn := setupAuthClients(cfg, logger)

	deps := proxyhttp.RouterDeps{
		Config:        cfg,
		Logger:        logger,
		Metrics:       meter,
		Validator:     validator,
		AgentVerifier: agentVerifier,
		Limiter:       limiter,
	}
	server := newHTTPServer(deps)
	runUntilShutdown(shutdownDeps{
		server:      server,
		logger:      logger,
		grpcConn:    grpcConn,
		redisClient: redisClient,
		serviceName: cfg.ServiceName,
	})
}

type shutdownDeps struct {
	server      *http.Server
	logger      *slog.Logger
	grpcConn    *grpc.ClientConn
	redisClient redis.UniversalClient
	serviceName string
}

func setupRateLimiter(cfg config.Config, logger *slog.Logger) (redis.UniversalClient, ratelimit.Limiter) {
	if cfg.RedisURL == "" {
		return nil, ratelimit.Noop()
	}
	client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
	if err != nil {
		logger.Error("redis client init failed", "error", err)
		os.Exit(1)
	}
	limiter := ratelimit.NewRedisSlider(client, rateLimitSliderConfig(cfg))
	logger.Info("rate limiter configured",
		"default_rpm", cfg.RateLimit.DefaultRPM,
		"org_overrides", len(cfg.RateLimit.OrgOverrides),
	)
	return client, limiter
}

func setupAuthClients(cfg config.Config, logger *slog.Logger) (auth.TokenValidator, auth.AgentVerifier, *grpc.ClientConn) {
	if cfg.AuthGRPCAddr == "" {
		return nil, nil, nil
	}
	conn, err := grpc.NewClient(cfg.AuthGRPCAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		logger.Error("auth grpc dial failed", "error", err, "addr", cfg.AuthGRPCAddr)
		os.Exit(1)
	}
	client := authv1.NewAuthServiceClient(conn)
	validator := auth.NewGRPCValidator(client, cfg.AuthValidateTimeout)
	agentVerifier := auth.NewGRPCAgentVerifier(client, cfg.AuthValidateTimeout)
	logger.Info("auth grpc client configured", "addr", cfg.AuthGRPCAddr, "timeout", cfg.AuthValidateTimeout.String())
	return validator, agentVerifier, conn
}

func newHTTPServer(deps proxyhttp.RouterDeps) *http.Server {
	return &http.Server{
		Addr:              ":" + deps.Config.Port,
		Handler:           proxyhttp.NewRouter(deps),
		ReadHeaderTimeout: 5 * time.Second,
	}
}

func runUntilShutdown(d shutdownDeps) {
	errCh := make(chan error, 1)
	go func() {
		d.logger.Info("service starting", "service", d.serviceName, "addr", d.server.Addr)
		if err := d.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-stop:
		d.logger.Info("shutdown signal received", "signal", sig.String())
	case err := <-errCh:
		if err != nil {
			d.logger.Error("server failed", "error", err)
			os.Exit(1)
		}
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := d.server.Shutdown(ctx); err != nil {
		d.logger.Error("graceful shutdown failed", "error", err)
		os.Exit(1)
	}
	if d.grpcConn != nil {
		_ = d.grpcConn.Close()
	}
	if d.redisClient != nil {
		_ = d.redisClient.Close()
	}
	d.logger.Info("service stopped", "service", d.serviceName)
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
