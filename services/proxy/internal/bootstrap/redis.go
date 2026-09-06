package bootstrap

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

// authCacheRedisPingTO bounds the startup Ping that gates auth-cache wrap.
const authCacheRedisPingTO = 2 * time.Second

func setupRateLimiter(cfg config.Config, log *logger.Logger) (redis.UniversalClient, ratelimit.Limiter, error) {
	if cfg.RedisURL == "" {
		return nil, ratelimit.Noop(), nil
	}
	client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
	if err != nil {
		return nil, nil, fmt.Errorf("redis client init: %w", err)
	}
	limiter, err := ratelimit.NewRedisSlider(client, rateLimitSliderConfig(cfg))
	if err != nil {
		return nil, nil, fmt.Errorf("redis slider: %w", err)
	}
	log.InfoCtx(context.Background(), "rate limiter configured",
		"default_rpm", cfg.RateLimit.DefaultRPM,
		"org_overrides", len(cfg.RateLimit.OrgOverrides),
	)
	return client, limiter, nil
}

func newIdempotencyStore(redisClient redis.UniversalClient, cfg config.Config) (idempotency.Store, error) {
	if redisClient == nil {
		return idempotency.Noop(), nil
	}
	return idempotency.NewRedisStore(redisClient, idempotency.Config{TTL: cfg.IdempotencyTTL})
}

type authClients struct {
	validator     auth.TokenValidator
	agentVerifier auth.AgentVerifier
	client        authv1.AuthServiceClient
	conn          *grpc.ClientConn
}

func setupAuthClients(
	cfg config.Config,
	log *logger.Logger,
	m *ibexmetrics.ProxyRegistry,
	redisClient redis.UniversalClient,
) (authClients, error) {
	if cfg.AuthGRPCAddr == "" {
		return authClients{}, nil
	}
	dialed, err := dialAuthGRPC(cfg)
	if err != nil {
		return authClients{}, err
	}
	validator, err := maybeWrapAuthCache(dialed.validator, cfg, authCacheDeps{
		log: log, metrics: m, redisClient: redisClient,
	})
	if err != nil {
		_ = dialed.conn.Close() //nolint:errcheck // best-effort cleanup; preserve wrap error
		return authClients{}, err
	}
	agentVerifier, err := auth.NewGRPCAgentVerifier(dialed.client, cfg.AuthValidateTimeout)
	if err != nil {
		_ = dialed.conn.Close() //nolint:errcheck // best-effort cleanup; preserve constructor error
		return authClients{}, fmt.Errorf("agent verifier: %w", err)
	}
	logAuthClientsConfigured(log, cfg, validator)
	return authClients{
		validator: validator, agentVerifier: agentVerifier,
		client: dialed.client, conn: dialed.conn,
	}, nil
}

type dialedAuthGRPC struct {
	conn      *grpc.ClientConn
	client    authv1.AuthServiceClient
	validator auth.TokenValidator
}

func dialAuthGRPC(cfg config.Config) (dialedAuthGRPC, error) {
	conn, err := grpc.NewClient(cfg.AuthGRPCAddr,
		grpc.WithTransportCredentials(authTransportCredentials(cfg.Environment)),
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
	if err != nil {
		return dialedAuthGRPC{}, fmt.Errorf("auth grpc dial addr=%s: %w", cfg.AuthGRPCAddr, err)
	}
	client := authv1.NewAuthServiceClient(conn)
	grpcValidator, err := auth.NewGRPCValidator(client, cfg.AuthValidateTimeout)
	if err != nil {
		_ = conn.Close() //nolint:errcheck // best-effort cleanup; preserve constructor error
		return dialedAuthGRPC{}, fmt.Errorf("auth validator: %w", err)
	}
	return dialedAuthGRPC{conn: conn, client: client, validator: grpcValidator}, nil
}

func logAuthClientsConfigured(log *logger.Logger, cfg config.Config, validator auth.TokenValidator) {
	_, cacheActive := validator.(auth.CacheInvalidator)
	log.InfoCtx(context.Background(), "auth grpc client configured",
		"addr", cfg.AuthGRPCAddr,
		"timeout", cfg.AuthValidateTimeout.String(),
		"auth_cache_enabled", cfg.AuthCache.Enabled,
		"auth_cache_active", cacheActive,
		"tls", cfg.Environment != "development",
	)
}

type contextClients struct {
	client *contextclient.Client
	conn   *grpc.ClientConn
}

func setupContextClient(cfg config.Config, log *logger.Logger) (contextClients, error) {
	if strings.TrimSpace(cfg.ContextGRPCTarget) == "" {
		return contextClients{}, nil
	}
	dialed, err := dialContextGRPC(cfg, log)
	if err != nil {
		return contextClients{}, err
	}
	return dialed, nil
}

func dialContextGRPC(cfg config.Config, log *logger.Logger) (contextClients, error) {
	conn, err := grpc.NewClient(cfg.ContextGRPCTarget,
		// Same env-gated transport as dialAuthGRPC: plaintext only in development.
		// Staging/production use TLS12. Do not force TLS in development — local auth/context
		// stacks run without certs (acceptable risk; mirrors auth client).
		grpc.WithTransportCredentials(authTransportCredentials(cfg.Environment)), // nosemgrep: go.grpc.tls.grpc-client-new-insecure-connection.grpc-client-new-insecure-connection
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
	if err != nil {
		return contextClients{}, fmt.Errorf("context grpc dial target=%s: %w", cfg.ContextGRPCTarget, err)
	}
	stub := contextv1.NewContextAssemblyServiceClient(conn)
	client, err := contextclient.New(stub, cfg.ContextAssembleTimeout, log)
	if err != nil {
		_ = conn.Close() //nolint:errcheck // best-effort cleanup; preserve constructor error
		return contextClients{}, fmt.Errorf("context client: %w", err)
	}
	log.InfoCtx(context.Background(), "context grpc client configured",
		"target", cfg.ContextGRPCTarget,
		"timeout", cfg.ContextAssembleTimeout.String(),
		"tls", cfg.Environment != "development",
	)
	return contextClients{client: client, conn: conn}, nil
}

func authTransportCredentials(environment string) credentials.TransportCredentials {
	if environment == "" || environment == "development" {
		return insecure.NewCredentials()
	}
	return credentials.NewTLS(&tls.Config{MinVersion: tls.VersionTLS12})
}

// authCacheDeps groups logger, metrics, and Redis for auth-cache wrap gating.
type authCacheDeps struct {
	log         *logger.Logger
	metrics     *ibexmetrics.ProxyRegistry
	redisClient redis.UniversalClient
}

func maybeWrapAuthCache(
	validator auth.TokenValidator,
	cfg config.Config,
	deps authCacheDeps,
) (auth.TokenValidator, error) {
	if !cfg.AuthCache.Enabled {
		return validator, nil
	}
	if reason, pingErr := authCacheUnavailableReason(deps.redisClient); reason != "" {
		warnAuthCacheSkipped(deps.log, reason, pingErr != nil)
		return validator, nil
	}
	return wrapAuthCache(validator, cfg, deps.log, deps.metrics)
}

func warnAuthCacheSkipped(log *logger.Logger, reason string, pingFailed bool) {
	attrs := []any{
		"reason", reason,
		"IBEX_AUTH_CACHE_ENABLED", true,
	}
	if pingFailed {
		// Stable class only — raw dial errors may embed host/IP (never log those).
		attrs = append(attrs, "failure_class", "redis_ping_failed")
	}
	log.WarnCtx(context.Background(),
		"auth cache disabled; revocation channel unavailable",
		attrs...,
	)
}

// authCacheUnavailableReason is the single gate for wrap-skip: empty reason means
// Redis can host the revocation subscriber. Non-empty reason is redis_url_empty
// or redis_ping_failed. The returned error is for control flow only (never log/trace).
func authCacheUnavailableReason(redisClient redis.UniversalClient) (string, error) {
	if redisClient == nil {
		return "redis_url_empty", nil
	}
	if err := pingRedisForAuthCache(redisClient); err != nil {
		return "redis_ping_failed", err
	}
	return "", nil
}

func pingRedisForAuthCache(client redis.UniversalClient) error {
	ctx, cancel := context.WithTimeout(context.Background(), authCacheRedisPingTO)
	defer cancel()
	ctx, span := otel.Tracer("ibex-proxy").Start(ctx, "bootstrap.Redis.Ping",
		trace.WithAttributes(
			attribute.String("db.system", "redis"),
			attribute.String("db.operation", "PING"),
		),
	)
	defer span.End()
	err := client.Ping(ctx).Err()
	if err != nil {
		// Classify without embedding dial target (may contain IP) in span status/events.
		failureClass := classifyRedisPingFailure(err)
		span.SetAttributes(attribute.String("error.type", failureClass))
		span.SetStatus(codes.Error, failureClass)
		return err
	}
	return nil
}

func classifyRedisPingFailure(err error) string {
	if err == nil {
		return ""
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		return "timeout"
	}
	return "redis_ping_failed"
}

func wrapAuthCache(
	validator auth.TokenValidator,
	cfg config.Config,
	log *logger.Logger,
	m *ibexmetrics.ProxyRegistry,
) (auth.TokenValidator, error) {
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
	log.InfoCtx(context.Background(),
		"auth cache wrapped; revocation subscriber will connect via Redis")
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
