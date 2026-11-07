package bootstrap

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/policysnapshot"
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

// contextCallerAuthProbeTO bounds the startup caller-auth probe. It stays short
// so a wedged context service cannot stall proxy startup.
const contextCallerAuthProbeTO = 1500 * time.Millisecond

// callerAuthServiceToken is the fixed log label for the ADR-0096 caller-auth
// scheme. Log labels are conventions, not values: keep them identical everywhere.
const callerAuthServiceToken = "service-token"

func setupRateLimiter(cfg config.Config, log *logger.Logger) (redis.UniversalClient, ratelimit.Limiter, error) {
	if cfg.RedisURL == "" {
		return nil, ratelimit.Noop(), nil
	}
	client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
	if err != nil {
		return nil, nil, fmt.Errorf("redis client init: %w", err)
	}
	limiter, err := ratelimit.NewHierarchicalLimiter(client, rateLimitHierarchicalConfig(cfg))
	if err != nil {
		return nil, nil, fmt.Errorf("hierarchical limiter: %w", err)
	}
	log.InfoCtx(context.Background(), "rate limiter configured",
		"default_rpm", cfg.RateLimit.DefaultRPM,
		"global_rpm", cfg.RateLimit.GlobalRPM,
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
	validator      auth.TokenValidator
	agentVerifier  auth.AgentVerifier
	policyFetcher  auth.PolicySnapshotFetcher
	policyVerifier *policysnapshot.Verifier
	client         authv1.AuthServiceClient
	conn           *grpc.ClientConn
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
	policyFetcher, policyVerifier, err := setupPolicySnapshot(cfg, log, dialed.client)
	if err != nil {
		_ = dialed.conn.Close() //nolint:errcheck // best-effort cleanup; preserve constructor error
		return authClients{}, err
	}
	logAuthClientsConfigured(log, cfg, validator, dialed.transport)
	return authClients{
		validator: validator, agentVerifier: agentVerifier,
		policyFetcher: policyFetcher, policyVerifier: policyVerifier,
		client: dialed.client, conn: dialed.conn,
	}, nil
}

// setupPolicySnapshot builds the GAP-002 issuance client and verifier when
// IBEX_PROXY_POLICY_PUBLIC_KEYS is configured; otherwise the stage stays off.
func setupPolicySnapshot(
	cfg config.Config,
	log *logger.Logger,
	client authv1.AuthServiceClient,
) (auth.PolicySnapshotFetcher, *policysnapshot.Verifier, error) {
	if strings.TrimSpace(cfg.PolicyPublicKeysJSON) == "" {
		return nil, nil, nil
	}
	keys, err := policysnapshot.ParseKeySetJSON(cfg.PolicyPublicKeysJSON)
	if err != nil {
		return nil, nil, fmt.Errorf("policy snapshot keys: %w", err)
	}
	verifier, err := policysnapshot.NewVerifier(policysnapshot.VerifierConfig{
		Keys: keys, MinEpoch: cfg.PolicyMinEpoch,
	})
	if err != nil {
		return nil, nil, fmt.Errorf("policy snapshot verifier: %w", err)
	}
	fetcher, err := auth.NewGRPCPolicySnapshotClient(client, cfg.AuthValidateTimeout)
	if err != nil {
		return nil, nil, fmt.Errorf("policy snapshot client: %w", err)
	}
	log.InfoCtx(context.Background(), "policy snapshot stage configured",
		"key_ids", len(keys.KeyIDs()),
		"min_epoch", cfg.PolicyMinEpoch,
	)
	return fetcher, verifier, nil
}

type dialedAuthGRPC struct {
	conn      *grpc.ClientConn
	client    authv1.AuthServiceClient
	validator auth.TokenValidator
	transport string
}

func dialAuthGRPC(cfg config.Config) (dialedAuthGRPC, error) {
	creds, err := authTransportCredentials(cfg.Environment, cfg.AuthGRPCCACertFile)
	if err != nil {
		return dialedAuthGRPC{}, fmt.Errorf("auth grpc transport credentials: %w", err)
	}
	conn, err := grpc.NewClient(cfg.AuthGRPCAddr,
		grpc.WithTransportCredentials(creds),
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
	return dialedAuthGRPC{
		conn: conn, client: client, validator: grpcValidator,
		transport: creds.Info().SecurityProtocol,
	}, nil
}

func logAuthClientsConfigured(log *logger.Logger, cfg config.Config, validator auth.TokenValidator, transport string) {
	_, cacheActive := validator.(auth.CacheInvalidator)
	log.InfoCtx(context.Background(), "auth grpc client configured",
		"addr", cfg.AuthGRPCAddr,
		"timeout", cfg.AuthValidateTimeout.String(),
		"auth_cache_enabled", cfg.AuthCache.Enabled,
		"auth_cache_active", cacheActive,
		"transport", transport,
		"custom_ca", strings.TrimSpace(cfg.AuthGRPCCACertFile) != "",
	)
}

type contextClients struct {
	client *contextclient.Client
	conn   *grpc.ClientConn
}

// setupContextClient builds the context client only when context assembly is
// enabled. A disabled or target-less config dials nothing, probes nothing, and
// never holds the service token.
func setupContextClient(cfg config.Config, log *logger.Logger, m *ibexmetrics.ProxyRegistry) (contextClients, error) {
	if !cfg.ContextEnabled || strings.TrimSpace(cfg.ContextGRPCTarget) == "" {
		return contextClients{}, nil
	}
	dialed, err := dialContextGRPC(cfg, log, m)
	if err != nil {
		return contextClients{}, err
	}
	if err := probeContextCallerAuth(dialed.client, log); err != nil {
		_ = dialed.conn.Close() //nolint:errcheck // best-effort cleanup; preserve probe error
		return contextClients{}, err
	}
	return dialed, nil
}

func dialContextGRPC(cfg config.Config, log *logger.Logger, m *ibexmetrics.ProxyRegistry) (contextClients, error) {
	creds, err := contextTransportCredentials(cfg)
	if err != nil {
		return contextClients{}, fmt.Errorf("context grpc transport credentials: %w", err)
	}
	conn, err := grpc.NewClient(cfg.ContextGRPCTarget,
		grpc.WithTransportCredentials(creds), // nosemgrep: go.grpc.tls.grpc-client-new-insecure-connection.grpc-client-new-insecure-connection
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
	if err != nil {
		return contextClients{}, fmt.Errorf("context grpc dial target=%s: %w", cfg.ContextGRPCTarget, err)
	}
	stub := contextv1.NewContextAssemblyServiceClient(conn)
	client, err := contextclient.New(stub, cfg.ContextAssembleTimeout, log, cfg.ContextGRPCServiceToken)
	if err != nil {
		_ = conn.Close() //nolint:errcheck // best-effort cleanup; preserve constructor error
		return contextClients{}, fmt.Errorf("context client: %w", err)
	}
	client.SetAssembleFallbackRecorder(m)
	log.InfoCtx(context.Background(), "context grpc client configured",
		"target", cfg.ContextGRPCTarget,
		"timeout", cfg.ContextAssembleTimeout.String(),
		"caller_auth", callerAuthServiceToken,
		"transport", contextTransportName(cfg),
	)
	return contextClients{client: client, conn: conn}, nil
}

// contextCallerAuthProber is satisfied by *contextclient.Client.
type contextCallerAuthProber interface {
	ProbeCallerAuth(ctx context.Context) error
}

// probeContextCallerAuth fails startup only when the context server rejects the
// service token. An unproven probe (UNIMPLEMENTED from the stub RPC) and a
// transport failure keep today's availability behaviour: warn and continue,
// because the chat path is already fail-open and the documented rollout starts
// the proxy before the guarded context image.
func probeContextCallerAuth(prober contextCallerAuthProber, log *logger.Logger) error {
	ctx, cancel := context.WithTimeout(context.Background(), contextCallerAuthProbeTO)
	defer cancel()
	err := prober.ProbeCallerAuth(ctx)
	if err == nil {
		log.InfoCtx(context.Background(), "context caller authentication probe passed",
			"caller_auth", callerAuthServiceToken, "rpc", "SearchMemories")
		return nil
	}
	if errors.Is(err, contextclient.ErrCallerAuthRejected) {
		return fmt.Errorf(
			"context caller authentication rejected: IBEX_CONTEXT_GRPC_SERVICE_TOKEN is missing or does not match the context server: %w",
			err,
		)
	}
	if errors.Is(err, contextclient.ErrCallerAuthUnproven) {
		log.WarnCtx(context.Background(),
			"context caller authentication unproven; the SearchMemories stub returning UNIMPLEMENTED does not prove the caller guard is installed",
			"caller_auth", callerAuthServiceToken, "rpc", "SearchMemories", "reason", err.Error())
		return nil
	}
	// Stable class only: the wrapped error carries the gRPC code, never the token.
	log.WarnCtx(context.Background(), "context caller authentication probe inconclusive; continuing",
		"caller_auth", callerAuthServiceToken, "reason", err.Error())
	return nil
}

// authTransportCredentials requires a per-install CA outside development.
// A configured CA always selects TLS, including development.
func authTransportCredentials(environment, caFile string) (credentials.TransportCredentials, error) {
	if path := strings.TrimSpace(caFile); path != "" {
		pool, err := loadAuthCA(path)
		if err != nil {
			return nil, err
		}
		return credentials.NewTLS(&tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}), nil
	}
	if environment == "development" {
		return insecure.NewCredentials(), nil
	}
	return nil, fmt.Errorf("IBEX_AUTH_GRPC_CA_FILE is required outside development")
}

// loadAuthCA reads the per-install CA bundle. The error names the variable and
// includes the path from the underlying *PathError; the path is not secret and
// the error is only returned at startup, never per request.
func loadAuthCA(path string) (*x509.CertPool, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("IBEX_AUTH_GRPC_CA_FILE: cannot read CA bundle: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(raw) {
		return nil, fmt.Errorf("IBEX_AUTH_GRPC_CA_FILE contains no parseable PEM certificate")
	}
	return pool, nil
}

// contextTransportCredentials selects the transport for the context hop.
// ADR-0097 §4 permits plaintext only on loopback inside one network namespace:
// when the profile declares the context process co-located (network_mode
// "service:proxy", binding a loopback literal), the hop is plaintext by design.
// Outside development, a non-co-located proxy still dials TLS rather
// than silently sending a cleartext service token. The auth dial is never
// affected by this decision, and the context hop never uses the auth CA.
func contextTransportCredentials(cfg config.Config) (credentials.TransportCredentials, error) {
	if cfg.ContextColocated || cfg.Environment == "development" {
		return insecure.NewCredentials(), nil
	}
	// Context retains system trust; the AuthService CA belongs only to that hop.
	return credentials.NewTLS(&tls.Config{MinVersion: tls.VersionTLS12}), nil
}

// contextTransportName reports the transport contextTransportCredentials
// selects, derived from the credential itself so the label cannot drift from
// the dial. It exists because a co-located production hop is plaintext, and
// logging "tls" for it would be false.
func contextTransportName(cfg config.Config) string {
	if cfg.ContextColocated {
		return "plaintext-loopback-colocated"
	}
	if cfg.Environment == "development" {
		return "plaintext-development"
	}
	return "tls"
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
func rateLimitHierarchicalConfig(cfg config.Config) ratelimit.HierarchicalConfig {
	overrides := make(map[uuid.UUID]int64, len(cfg.RateLimit.OrgOverrides))
	for orgID, rpm := range cfg.RateLimit.OrgOverrides {
		overrides[orgID] = int64(rpm)
	}
	return ratelimit.HierarchicalConfig{
		DefaultRPM:   int64(cfg.RateLimit.DefaultRPM),
		OrgOverrides: overrides,
		GlobalRPM:    int64(cfg.RateLimit.GlobalRPM),
	}
}
