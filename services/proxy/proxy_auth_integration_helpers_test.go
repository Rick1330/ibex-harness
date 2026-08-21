//go:build integration

package proxy_test

import (
	"context"
	"database/sql"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/integrationtest"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type proxyAuthFixture struct {
	db             *sql.DB
	authFx         *integrationtest.AuthGRPCFixture
	srv            *httptest.Server
	orgA           string
	orgB           string
	agentA         string
	agentB         string
	validBearer    string
	chatBearer     string
	revokedBearer  string
	orgBBearer     string
	lowPermsBearer string
}

func setupProxyAuthFixture(t *testing.T) proxyAuthFixture {
	return setupProxyAuthFixtureWithProviders(t, nil)
}

func setupProxyAuthFixtureWithProviders(t *testing.T, providers []provider.Provider) proxyAuthFixture {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	authFx := integrationtest.StartAuthGRPC(t, dsn)
	t.Cleanup(authFx.Close)

	orgA := testutil.SeedOrganization(t, db, "Org A", "org-a-proxy-"+uuid.NewString()[:8])
	orgB := testutil.SeedOrganization(t, db, "Org B", "org-b-proxy-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgA, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgB, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")
	agentA := testutil.SeedAgent(t, db, orgA, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgB, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])

	validBearer, _ := testutil.SeedToken(t, db, orgA, 42)
	chatBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ProxyChatCompletion)
	revokedBearer := testutil.SeedTokenRevoked(t, db, orgA, 42)
	orgBBearer, _ := testutil.SeedToken(t, db, orgB, 42)
	lowPermsBearer, _ := testutil.SeedToken(t, db, orgA, permissions.ReadOnly)

	srv := startProxyServer(t, authFx.Addr, proxyServerOpts{providers: providers})
	t.Cleanup(srv.Close)

	return proxyAuthFixture{
		db: db, authFx: authFx, srv: srv,
		orgA: orgA, orgB: orgB, agentA: agentA, agentB: agentB,
		validBearer: validBearer, chatBearer: chatBearer, revokedBearer: revokedBearer,
		orgBBearer: orgBBearer, lowPermsBearer: lowPermsBearer,
	}
}

type testOrgContext struct {
	OrgID   string
	UserID  string
	AgentID string
	Token   string
}

type securityTestEnv struct {
	db      *sql.DB
	authFx  *integrationtest.AuthGRPCFixture
	proxy   *httptest.Server
	redisMR *miniredis.Miniredis
	orgA    testOrgContext
	orgB    testOrgContext
}

type redisFixture struct {
	url    string
	client redis.UniversalClient
	mr     *miniredis.Miniredis
}

type proxyServerOpts struct {
	defaultRPM    int64
	orgOverrides  map[uuid.UUID]int64
	providers     []provider.Provider
	withAuthCache bool // bloom+LRU + revocation subscriber when Redis present (SEC7)
	skipRedis     bool // empty REDIS_URL — Wave 4: cache must not wrap
}

func setupSecurityTestEnv(t *testing.T, srvOpts proxyServerOpts) securityTestEnv {
	t.Helper()
	dsn, cleanup := testutil.SetupPostgres(t)
	t.Cleanup(cleanup)

	db := testutil.OpenDB(t, dsn)
	t.Cleanup(func() { _ = db.Close() })

	redis := optionalTestRedis(t, srvOpts.skipRedis)
	var authFx *integrationtest.AuthGRPCFixture
	if srvOpts.withAuthCache && redis.client != nil {
		authFx = integrationtest.StartAuthGRPCWithRedis(t, dsn, redis.client)
	} else {
		authFx = integrationtest.StartAuthGRPC(t, dsn)
	}
	t.Cleanup(authFx.Close)

	orgAID := testutil.SeedOrganization(t, db, "Org A", "org-a-sec-"+uuid.NewString()[:8])
	orgBID := testutil.SeedOrganization(t, db, "Org B", "org-b-sec-"+uuid.NewString()[:8])
	userA := testutil.SeedUser(t, db, orgAID, "user-a-"+uuid.NewString()[:8]+"@example.com", "User A")
	userB := testutil.SeedUser(t, db, orgBID, "user-b-"+uuid.NewString()[:8]+"@example.com", "User B")
	agentA := testutil.SeedAgent(t, db, orgAID, userA, "Agent A", "agent-a-"+uuid.NewString()[:8])
	agentB := testutil.SeedAgent(t, db, orgBID, userB, "Agent B", "agent-b-"+uuid.NewString()[:8])
	tokenA, _ := testutil.SeedToken(t, db, orgAID, 42)
	tokenB, _ := testutil.SeedToken(t, db, orgBID, 42)

	proxy := startProxyServerRedis(t, authFx.Addr, srvOpts, redis)
	t.Cleanup(proxy.Close)

	return securityTestEnv{
		db: db, authFx: authFx, proxy: proxy, redisMR: redis.mr,
		orgA: testOrgContext{OrgID: orgAID, UserID: userA, AgentID: agentA, Token: tokenA},
		orgB: testOrgContext{OrgID: orgBID, UserID: userB, AgentID: agentB, Token: tokenB},
	}
}

func setupTestRedis(t *testing.T) redisFixture {
	t.Helper()
	mr := miniredis.RunT(t)
	url := "redis://" + mr.Addr() + "/0"
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return redisFixture{url: url, client: client, mr: mr}
}

func optionalTestRedis(t *testing.T, skip bool) redisFixture {
	t.Helper()
	if skip {
		return redisFixture{}
	}
	return setupTestRedis(t)
}

// redisReadyForAuthCache mirrors bootstrap authCacheUnavailableReason: non-nil
// client and successful Ping are required before wrapping the auth cache.
func redisReadyForAuthCache(client redis.UniversalClient) bool {
	if client == nil {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	return client.Ping(ctx).Err() == nil
}

func startProxyServer(t *testing.T, authAddr string, srvOpts proxyServerOpts) *httptest.Server {
	t.Helper()
	return startProxyServerRedis(t, authAddr, srvOpts, setupTestRedis(t))
}

func startProxyServerRedis(t *testing.T, authAddr string, srvOpts proxyServerOpts, redis redisFixture) *httptest.Server {
	t.Helper()
	conn, err := grpc.NewClient(authAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithChainUnaryInterceptor(proxygrpc.RequestIDUnaryInterceptor()),
	)
	if err != nil {
		t.Fatalf("dial auth: %v", err)
	}
	t.Cleanup(func() { _ = conn.Close() })

	cfg := proxyIntegrationConfig(authAddr, redis.url, srvOpts)
	client := authv1.NewAuthServiceClient(conn)
	handler := newProxyIntegrationHandler(t, proxyIntegrationHandlerOpts{
		cfg: cfg, client: client, redisClient: redis.client, srvOpts: srvOpts,
	})
	return httptest.NewServer(handler)
}

func proxyIntegrationConfig(authAddr, redisURL string, srvOpts proxyServerOpts) config.Config {
	defaultRPM := srvOpts.defaultRPM
	if defaultRPM < 1 {
		defaultRPM = 60
	}
	cfg := config.Config{
		Environment:         "development",
		ServiceName:         "proxy",
		Port:                "8080",
		RedisURL:            redisURL,
		AuthGRPCAddr:        authAddr,
		AuthValidateTimeout: 200 * time.Millisecond,
		RateLimit: config.RateLimitConfig{
			DefaultRPM: int(defaultRPM),
		},
	}
	if srvOpts.withAuthCache {
		cfg.AuthCache = config.AuthCacheConfig{
			Enabled:            true,
			LRUCapacity:        256,
			LRUMaxTTL:          30 * time.Second,
			BloomExpectedItems: 1000,
			BloomFPRate:        0.01,
		}
	}
	return cfg
}

type proxyIntegrationHandlerOpts struct {
	cfg         config.Config
	client      authv1.AuthServiceClient
	redisClient redis.UniversalClient
	srvOpts     proxyServerOpts
}

func newProxyIntegrationHandler(t *testing.T, opts proxyIntegrationHandlerOpts) http.Handler {
	t.Helper()
	defaultRPM := opts.srvOpts.defaultRPM
	if defaultRPM < 1 {
		defaultRPM = 60
	}
	orgOverrides := opts.srvOpts.orgOverrides
	if orgOverrides == nil {
		orgOverrides = map[uuid.UUID]int64{}
	}

	validator := mustGRPCValidator(t, opts.client, opts.cfg.AuthValidateTimeout)
	// Mirror bootstrap maybeWrapAuthCache (Wave 4): wrap only when Redis Ping succeeds.
	// Enabled flag alone must not create a stale LRU.
	if opts.srvOpts.withAuthCache && redisReadyForAuthCache(opts.redisClient) {
		validator = mustCachedValidator(t, validator)
		revokeCtx, revokeCancel := context.WithCancel(context.Background())
		t.Cleanup(revokeCancel)
		startTestRevocationSubscriber(t, revokeCtx, opts.redisClient, validator)
	}
	agentVerifier := mustGRPCAgentVerifier(t, opts.client, opts.cfg.AuthValidateTimeout)
	limiter := mustProxyLimiter(t, opts.redisClient, defaultRPM, orgOverrides)
	providerReg := mustProviderRegistry(t, opts.srvOpts.providers...)
	healthCheckers := map[string]healthcheck.Checker{
		"auth_grpc": healthcheck.AuthGRPC(opts.client, opts.cfg.AuthValidateTimeout),
	}
	// Production always registers RedisPing (empty URL → readiness fail). Tests that
	// model intentional empty REDIS_URL omit it so /ready stays usable for SEC-7.3.
	if opts.cfg.RedisURL != "" {
		healthCheckers["redis"] = healthcheck.RedisPing(opts.cfg.RedisURL)
	}
	handler, err := proxyhttp.NewRouter(proxyhttp.RouterDeps{
		Config:           opts.cfg,
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        validator,
		AgentVerifier:    agentVerifier,
		Limiter:          limiter,
		Health:           &healthcheck.Server{CriticalCheckers: healthCheckers},
		ProviderRegistry: providerReg,
	})
	if err != nil {
		t.Fatalf("NewRouter: %v", err)
	}
	return handler
}

func mustCachedValidator(t *testing.T, inner auth.TokenValidator) auth.TokenValidator {
	t.Helper()
	wrapped, err := auth.WrapWithCache(inner, authcache.Config{
		LRUCapacity:        256,
		LRUMaxTTL:          30 * time.Second,
		BloomExpectedItems: 1000,
		BloomFPRate:        0.01,
	}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err != nil {
		t.Fatalf("WrapWithCache: %v", err)
	}
	return wrapped
}

func startTestRevocationSubscriber(t *testing.T, ctx context.Context, client redis.UniversalClient, validator auth.TokenValidator) {
	t.Helper()
	inv, ok := validator.(auth.CacheInvalidator)
	if !ok {
		t.Fatal("cached validator must implement CacheInvalidator")
	}
	sub, err := revocation.NewSubscriber(client, inv, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("revocation subscriber: %v", err)
	}
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		sub.Run(ctx)
	}()
	t.Cleanup(func() {
		sub.Stop()
		select {
		case <-sub.Done():
		case <-time.After(2 * time.Second):
			t.Error("timeout waiting for revocation subscriber shutdown")
		}
		wg.Wait()
	})
	require.Eventually(t, func() bool {
		inspectCtx, cancel := context.WithTimeout(ctx, 250*time.Millisecond)
		defer cancel()
		n, err := client.PubSubNumSub(inspectCtx, revocation.Channel).Result()
		return err == nil && n[revocation.Channel] > 0
	}, 2*time.Second, 10*time.Millisecond, "timeout waiting for revocation subscriber")
}

func mustGRPCValidator(t *testing.T, client authv1.AuthServiceClient, timeout time.Duration) auth.TokenValidator {
	t.Helper()
	v, err := auth.NewGRPCValidator(client, timeout)
	if err != nil {
		t.Fatalf("NewGRPCValidator: %v", err)
	}
	return v
}

func mustGRPCAgentVerifier(t *testing.T, client authv1.AuthServiceClient, timeout time.Duration) auth.AgentVerifier {
	t.Helper()
	v, err := auth.NewGRPCAgentVerifier(client, timeout)
	if err != nil {
		t.Fatalf("NewGRPCAgentVerifier: %v", err)
	}
	return v
}

func mustRedisSlider(t *testing.T, client redis.UniversalClient, defaultRPM int64, orgOverrides map[uuid.UUID]int64) ratelimit.Limiter {
	t.Helper()
	limiter, err := ratelimit.NewRedisSlider(client, ratelimit.RedisSliderConfig{
		DefaultRPM:   defaultRPM,
		OrgOverrides: orgOverrides,
	})
	if err != nil {
		t.Fatalf("NewRedisSlider: %v", err)
	}
	return limiter
}

func mustProxyLimiter(t *testing.T, client redis.UniversalClient, defaultRPM int64, orgOverrides map[uuid.UUID]int64) ratelimit.Limiter {
	t.Helper()
	if client == nil {
		return ratelimit.Noop()
	}
	return mustRedisSlider(t, client, defaultRPM, orgOverrides)
}

func mustProviderRegistry(t *testing.T, providers ...provider.Provider) *provider.Registry {
	t.Helper()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), providers...)
	if err != nil {
		t.Fatalf("provider registry: %v", err)
	}
	return reg
}

type authProbeOpts struct {
	srvURL  string
	bearer  string
	agentID string
}

func authProbeGET(t *testing.T, opts authProbeOpts) (*http.Response, string) {
	t.Helper()
	return authenticatedGET(t, opts.srvURL+"/v1/internal/auth-probe", opts.bearer, opts.agentID)
}

type orgAuthProbeOpts struct {
	srvURL  string
	orgID   string
	bearer  string
	agentID string
}

func orgAuthProbeGET(t *testing.T, opts orgAuthProbeOpts) (*http.Response, string) {
	t.Helper()
	return authenticatedGET(t, opts.srvURL+"/v1/orgs/"+opts.orgID+"/auth-probe", opts.bearer, opts.agentID)
}

func authenticatedGET(t *testing.T, url, bearer, agentID string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		t.Fatal(err)
	}
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	if agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}

type chatRequestOpts struct {
	srvURL      string
	bearer      string
	agentID     string
	contentType string
	body        string
}

func chatPOST(t *testing.T, opts chatRequestOpts) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, opts.srvURL+"/v1/chat/completions", strings.NewReader(opts.body))
	if err != nil {
		t.Fatal(err)
	}
	if opts.bearer != "" {
		req.Header.Set("Authorization", "Bearer "+opts.bearer)
	}
	if opts.contentType != "" {
		req.Header.Set("Content-Type", opts.contentType)
	}
	if opts.agentID != "" {
		req.Header.Set("X-IBEX-Agent-ID", opts.agentID)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}

func seedPausedAgent(t *testing.T, db *sql.DB, orgID, userID string) string {
	t.Helper()
	pausedID := uuid.New().String()
	err := testutil.WithServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), `
			INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
			VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 'paused')`,
			pausedID, orgID, userID, "Paused Agent", "paused-"+uuid.NewString()[:8],
		)
		return err
	})
	if err != nil {
		t.Fatalf("seed paused agent: %v", err)
	}
	return pausedID
}

func readBody(resp *http.Response) string {
	b, _ := io.ReadAll(resp.Body)
	return string(b)
}

func assertResponseHeaders(t *testing.T, resp *http.Response) {
	t.Helper()
	if resp.Header.Get("X-Request-ID") == "" {
		t.Fatal("missing X-Request-ID response header")
	}
	if resp.Header.Get("X-Trace-ID") == "" {
		t.Fatal("missing X-Trace-ID response header")
	}
	if resp.Header.Get("X-Response-Time") == "" {
		t.Fatal("missing X-Response-Time response header")
	}
}
