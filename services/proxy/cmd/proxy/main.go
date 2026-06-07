package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
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
	runWithShutdown(shutdownOpts{
		cfg: cfg, logger: logger, server: server,
		grpcConn: grpcConn, redisClient: redisClient,
	})
}

type shutdownOpts struct {
	cfg         config.Config
	logger      *slog.Logger
	server      *http.Server
	grpcConn    *grpc.ClientConn
	redisClient redis.UniversalClient
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
	conn, err := grpc.NewClient(cfg.AuthGRPCAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
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

func runWithShutdown(opts shutdownOpts) {
	errCh := make(chan error, 1)
	go func() {
		opts.logger.Info("service starting", "service", opts.cfg.ServiceName, "addr", opts.server.Addr)
		if err := opts.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	sd := shutdown.New(opts.cfg.ShutdownTimeout, opts.logger)
	sd.Register(func(ctx context.Context) error {
		return opts.server.Shutdown(ctx)
	})
	sd.Register(func(ctx context.Context) error {
		if opts.grpcConn != nil {
			return opts.grpcConn.Close()
		}
		return nil
	})
	sd.Register(func(ctx context.Context) error {
		if opts.redisClient != nil {
			return opts.redisClient.Close()
		}
		return nil
	})

	shutdownErrCh := make(chan error, 1)
	go func() {
		shutdownErrCh <- sd.Wait()
	}()

	select {
	case err := <-errCh:
		if err != nil {
			opts.logger.Error("server failed", "error", err)
			os.Exit(1)
		}
	case err := <-shutdownErrCh:
		if err != nil {
			os.Exit(1)
		}
		opts.logger.Info("service stopped", "service", opts.cfg.ServiceName)
	}
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
