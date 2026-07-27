package bootstrap

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

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

func newIdempotencyStore(redisClient redis.UniversalClient, cfg config.Config) idempotency.Store {
	if redisClient == nil {
		return idempotency.Noop()
	}
	return idempotency.NewRedisStore(redisClient, idempotency.Config{TTL: cfg.IdempotencyTTL})
}

func setupAuthClients(cfg config.Config, log *logger.Logger, m *ibexmetrics.ProxyRegistry) (auth.TokenValidator, auth.AgentVerifier, authv1.AuthServiceClient, *grpc.ClientConn, error) {
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
	var validator auth.TokenValidator = auth.NewGRPCValidator(client, cfg.AuthValidateTimeout)
	validator, err = maybeWrapAuthCache(validator, cfg, log, m)
	if err != nil {
		_ = conn.Close()
		return nil, nil, nil, nil, err
	}
	agentVerifier := auth.NewGRPCAgentVerifier(client, cfg.AuthValidateTimeout)
	log.InfoCtx(context.Background(), "auth grpc client configured",
		"addr", cfg.AuthGRPCAddr,
		"timeout", cfg.AuthValidateTimeout.String(),
		"auth_cache_enabled", cfg.AuthCache.Enabled,
	)
	return validator, agentVerifier, client, conn, nil
}

func maybeWrapAuthCache(
	validator auth.TokenValidator,
	cfg config.Config,
	log *logger.Logger,
	m *ibexmetrics.ProxyRegistry,
) (auth.TokenValidator, error) {
	if !cfg.AuthCache.Enabled {
		return validator, nil
	}
	var metrics authcache.Metrics = authcache.NoopMetrics{}
	if m != nil {
		metrics = m
	}
	wrapped, err := auth.WrapWithCache(validator, authcache.Config{
		LRUCapacity:        cfg.AuthCache.LRUCapacity,
		LRUMaxTTL:          cfg.AuthCache.LRUMaxTTL,
		BloomExpectedItems: cfg.AuthCache.BloomExpectedItems,
		BloomFPRate:        cfg.AuthCache.BloomFPRate,
	}, log, metrics)
	if err != nil {
		return nil, fmt.Errorf("auth cache: %w", err)
	}
	return wrapped, nil
}

func startRevocationSubscriber(
	redisClient redis.UniversalClient,
	validator auth.TokenValidator,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
) (*revocation.Subscriber, context.CancelFunc, error) {
	if redisClient == nil {
		return nil, nil, nil
	}
	inv, ok := validator.(auth.CacheInvalidator)
	if !ok {
		log.InfoCtx(context.Background(), "revocation subscriber skipped; auth cache disabled")
		return nil, nil, nil
	}
	sub, err := revocation.NewSubscriber(redisClient, inv, log, reg)
	if err != nil {
		return nil, nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	go sub.Run(ctx)
	log.InfoCtx(context.Background(), "revocation subscriber started", "channel", revocation.Channel)
	return sub, cancel, nil
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
