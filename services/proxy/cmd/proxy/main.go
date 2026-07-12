package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	return runBootstrap(args, nil)
}

// providerRegistryInit is overridden in tests to simulate startup registry failures.
var providerRegistryInit = provider.NewRegistry

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

	providers, tracer, err := telemetry.InitTracer(context.Background(), cfg.Telemetry, "ibex-proxy")
	if err != nil {
		log.ErrorCtx(context.Background(), "telemetry init failed", "error", err)
		return 1
	}
	reg := ibexmetrics.NewProxy(cfg.ServiceName)
	redisClient, limiter, err := setupRateLimiter(cfg, log)
	if err != nil {
		log.ErrorCtx(context.Background(), "rate limiter setup failed", "error", err)
		return 1
	}
	validator, agentVerifier, authClient, grpcConn, err := setupAuthClients(cfg, log)
	if err != nil {
		log.ErrorCtx(context.Background(), "auth client setup failed", "error", err)
		return 1
	}

	healthSrv := &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"auth_grpc": healthcheck.AuthGRPC(authClient, cfg.AuthValidateTimeout),
			"redis":     healthcheck.RedisPing(cfg.RedisURL),
		},
	}

	providerReg, err := providerRegistryInit()
	if err != nil {
		log.ErrorCtx(context.Background(), "provider registry init failed", "error", err)
		return 1
	}

	deps := proxyhttp.RouterDeps{
		Config:           cfg,
		Logger:           log,
		Metrics:          reg,
		Tracer:           tracer,
		Validator:        validator,
		AgentVerifier:    agentVerifier,
		Limiter:          limiter,
		Health:           healthSrv,
		ProviderRegistry: providerReg,
	}
	server := newHTTPServer(deps)
	return runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, providers: providers, server: server,
		grpcConn: grpcConn, redisClient: redisClient, signalCh: signalCh,
	})
}

type shutdownOpts struct {
	cfg         config.Config
	logger      *logger.Logger
	server      *http.Server
	providers   *telemetry.Providers
	grpcConn    *grpc.ClientConn
	redisClient redis.UniversalClient
	signalCh    chan os.Signal
}

func setupRateLimiter(cfg config.Config, log *logger.Logger) (redis.UniversalClient, ratelimit.Limiter, error) {
	if cfg.RedisURL == "" {
		return nil, ratelimit.Noop(), nil
	}
	client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
	if err != nil {
		return nil, nil, fmt.Errorf("redis client init: %w", err)
	}
	limiter := ratelimit.NewRedisSlider(client, rateLimitSliderConfig(cfg))
	log.InfoCtx(context.Background(), "rate limiter configured",
		"default_rpm", cfg.RateLimit.DefaultRPM,
		"org_overrides", len(cfg.RateLimit.OrgOverrides),
	)
	return client, limiter, nil
}

func setupAuthClients(cfg config.Config, log *logger.Logger) (auth.TokenValidator, auth.AgentVerifier, authv1.AuthServiceClient, *grpc.ClientConn, error) {
	if cfg.AuthGRPCAddr == "" {
		return nil, nil, nil, nil, nil
	}
	conn, err := grpc.NewClient(cfg.AuthGRPCAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
	if err != nil {
		return nil, nil, nil, nil, fmt.Errorf("auth grpc dial addr=%s: %w", cfg.AuthGRPCAddr, err)
	}
	client := authv1.NewAuthServiceClient(conn)
	validator := auth.NewGRPCValidator(client, cfg.AuthValidateTimeout)
	agentVerifier := auth.NewGRPCAgentVerifier(client, cfg.AuthValidateTimeout)
	log.InfoCtx(context.Background(), "auth grpc client configured", "addr", cfg.AuthGRPCAddr, "timeout", cfg.AuthValidateTimeout.String())
	return validator, agentVerifier, client, conn, nil
}

func newHTTPServer(deps proxyhttp.RouterDeps) *http.Server {
	return &http.Server{
		Addr:              ":" + deps.Config.Port,
		Handler:           proxyhttp.NewRouter(deps),
		ReadHeaderTimeout: 5 * time.Second,
	}
}

func runWithShutdown(opts shutdownOpts) int {
	errCh := make(chan error, 1)
	go func() {
		opts.logger.InfoCtx(context.Background(), "service starting", "addr", opts.server.Addr)
		if err := opts.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	var sd *shutdown.Coordinator
	if opts.signalCh != nil {
		sd = shutdown.NewWithSignalChan(opts.cfg.ShutdownTimeout, opts.logger, opts.signalCh)
	} else {
		sd = shutdown.New(opts.cfg.ShutdownTimeout, opts.logger)
	}
	registerShutdownHooks(sd, opts)

	shutdownErrCh := make(chan error, 1)
	go func() {
		shutdownErrCh <- sd.Wait()
	}()

	select {
	case err := <-errCh:
		if err != nil {
			opts.logger.ErrorCtx(context.Background(), "server failed", "error", err)
			return 1
		}
	case err := <-shutdownErrCh:
		if err != nil {
			return 1
		}
		opts.logger.InfoCtx(context.Background(), "service stopped")
	}
	return 0
}

func registerShutdownHooks(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(opts.providers.Shutdown)
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
