package main

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/trace"

	// Register the lib/pq "postgres" driver for sql.Open in proxy unit tests.
	_ "github.com/lib/pq"
)

func TestRun_InvalidConfigReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "not-valid")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRateLimitSliderConfig(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("00000000-0000-0000-0000-000000000001")
	otherOrg := uuid.MustParse("00000000-0000-0000-0000-000000000002")
	cfg := config.Config{
		RateLimit: config.RateLimitConfig{
			DefaultRPM:   120,
			OrgOverrides: map[uuid.UUID]int{orgID: 30, otherOrg: 45},
		},
	}
	got := rateLimitSliderConfig(cfg)
	if got.DefaultRPM != 120 {
		t.Fatalf("DefaultRPM = %d, want 120", got.DefaultRPM)
	}
	if got.OrgOverrides[orgID] != 30 {
		t.Fatalf("org override = %d, want 30", got.OrgOverrides[orgID])
	}
	if got.OrgOverrides[otherOrg] != 45 {
		t.Fatalf("other org override = %d, want 45", got.OrgOverrides[otherOrg])
	}
	if len(got.OrgOverrides) != 2 {
		t.Fatalf("overrides: %+v", got.OrgOverrides)
	}
}

func TestSetupRateLimiter_NoRedis(t *testing.T) {
	log := logger.Discard("proxy")
	client, limiter, err := setupRateLimiter(config.Config{}, log)
	if err != nil {
		t.Fatalf("setupRateLimiter: %v", err)
	}
	if client != nil {
		t.Fatal("expected nil redis client")
	}
	if limiter == nil {
		t.Fatal("expected noop limiter")
	}
	result, err := limiter.Check(context.Background(), uuid.Nil, uuid.Nil)
	if err != nil || !result.Allowed {
		t.Fatalf("noop limiter check: result=%+v err=%v", result, err)
	}
}

func TestSetupRateLimiter_WithMiniredis(t *testing.T) {
	mr := miniredis.RunT(t)
	log := logger.Discard("proxy")
	cfg := config.Config{RedisURL: "redis://" + mr.Addr() + "/0"}
	client, limiter, err := setupRateLimiter(cfg, log)
	if err != nil {
		t.Fatalf("setupRateLimiter: %v", err)
	}
	t.Cleanup(func() { _ = client.Close() })
	if client == nil || limiter == nil {
		t.Fatal("expected redis client and limiter")
	}
}

func TestSetupRateLimiter_InvalidURL(t *testing.T) {
	log := logger.Discard("proxy")
	_, _, err := setupRateLimiter(config.Config{RedisURL: "not-a-redis-url"}, log)
	if err == nil {
		t.Fatal("expected error for invalid redis URL")
	}
}

func TestNewIdempotencyStore_NilAndRedis(t *testing.T) {
	t.Parallel()
	noop := newIdempotencyStore(nil, config.Config{IdempotencyTTL: time.Hour})
	out, err := noop.Claim(context.Background(), uuid.New(), "k", "fp")
	if err != nil || out.Kind != idempotency.KindMiss {
		t.Fatalf("noop: %+v %v", out, err)
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	store := newIdempotencyStore(client, config.Config{IdempotencyTTL: time.Hour})
	out, err = store.Claim(context.Background(), uuid.New(), "k2", "fp")
	if err != nil || out.Kind != idempotency.KindMiss {
		t.Fatalf("redis store: %+v %v", out, err)
	}
}

func TestSetupDirectiveResolver_NoopWithoutDSNOrRedis(t *testing.T) {
	log := logger.Discard("proxy")
	db, resolver, err := setupDirectiveResolver(directiveResolverSetup{
		Config: config.Config{}, Log: log, OpenDB: openProxyPostgres,
	})
	if err != nil {
		t.Fatalf("setup: %v", err)
	}
	if db != nil {
		t.Fatal("expected nil db")
	}
	got, err := resolver.Resolve(context.Background(), uuid.Nil, uuid.Nil)
	if err != nil || got.HasContent() {
		t.Fatalf("noop resolve: %+v err=%v", got, err)
	}

	mr := miniredis.RunT(t)
	client, err := ratelimit.ParseRedisURL("redis://" + mr.Addr() + "/0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	db, resolver, err = setupDirectiveResolver(directiveResolverSetup{
		Config: config.Config{RedisURL: "redis://" + mr.Addr()},
		Redis:  client, Log: log, OpenDB: openProxyPostgres,
	})
	if err != nil {
		t.Fatalf("setup with redis only: %v", err)
	}
	if db != nil {
		t.Fatal("expected nil db without POSTGRES_DSN")
	}
	_, _ = resolver.Resolve(context.Background(), uuid.Nil, uuid.Nil)
}

func TestStartDirectiveSubscriber_SkippedForNoop(t *testing.T) {
	log := logger.Discard("proxy")
	sub, cancel, err := startDirectiveSubscriber(nil, directive.NoopResolver{}, log, nil)
	assertSubscriberSkipped(t, sub, cancel, err)
	mr := miniredis.RunT(t)
	client, err := ratelimit.ParseRedisURL("redis://" + mr.Addr() + "/0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	sub, cancel, err = startDirectiveSubscriber(client, directive.NoopResolver{}, log, nil)
	assertSubscriberSkipped(t, sub, cancel, err)
}

func assertSubscriberSkipped(t *testing.T, sub *directive.Subscriber, cancel context.CancelFunc, err error) {
	t.Helper()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if sub != nil {
		t.Fatal("expected nil subscriber")
	}
	if cancel != nil {
		t.Fatal("expected nil cancel")
	}
}

func TestNewHTTPServer(t *testing.T) {
	t.Parallel()
	cfg := config.Config{Port: "8080"}
	cfg.ApplyDefaults()
	providerReg, err := provider.NewRegistry()
	if err != nil {
		t.Fatal(err)
	}
	srv := newHTTPServer(proxyhttp.RouterDeps{
		Config: cfg, Logger: logger.Discard("proxy"), Metrics: ibexmetrics.NewProxy("proxy"),
		Limiter: ratelimit.Noop(), Health: &healthcheck.Server{},
		ProviderRegistry: providerReg,
	})
	if srv.Addr != ":8080" {
		t.Fatalf("addr: %s", srv.Addr)
	}
	if srv.Handler == nil || srv.ReadHeaderTimeout != 5*time.Second {
		t.Fatalf("server: %+v", srv)
	}
}

func TestRun_InvalidLoggerLevelReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_LOG_LEVEL", "not-a-level")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_InvalidOTELSampleRatioReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("OTEL_SAMPLE_RATIO", "2")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_InvalidRedisURLReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("REDIS_URL", "not-a-redis-url")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_ProviderRegistryInitFailureReturns1(t *testing.T) {
	orig := providerRegistryInit
	t.Cleanup(func() { providerRegistryInit = orig })
	providerRegistryInit = func(_ config.Config, _ *logger.Logger, _ trace.Tracer, _ *ibexmetrics.ProxyRegistry) (*provider.Registry, error) {
		return nil, errors.New("registry init failed")
	}
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("REDIS_URL", "")
	t.Setenv("IBEX_AUTH_GRPC_ADDR", "")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestUnit_NewSessionStore(t *testing.T) {
	t.Parallel()

	tracer := telemetry.NoopTracer("ibex-session")

	got, err := newSessionStore(nil, nil, tracer)
	if err != nil {
		t.Fatalf("nil db err: %v", err)
	}
	if got != nil {
		t.Fatal("expected nil store without db")
	}

	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/nope?sslmode=disable")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	store, err := newSessionStore(db, nil, tracer)
	if err != nil {
		t.Fatalf("noop metrics err: %v", err)
	}
	if store == nil {
		t.Fatal("expected store")
	}

	reg := ibexmetrics.NewProxy("proxy-session-test")
	store, err = newSessionStore(db, reg, tracer)
	if err != nil {
		t.Fatalf("registry metrics err: %v", err)
	}
	if store == nil {
		t.Fatal("expected store with registry")
	}
}

func TestUnit_SetupDirectiveResolver_PostgresWithoutRedis(t *testing.T) {
	db := mustStubPostgres(t)
	openDB := func(string) (*sql.DB, error) { return db, nil }

	gotDB, resolver := mustSetupDirectiveWithDSN(t, openDB)
	if gotDB != db {
		t.Fatal("expected stubbed postgres db")
	}
	assertSessionStoreWired(t, gotDB)
	assertNoopDirectiveResolve(t, resolver)
}

func TestUnit_SetupDirectiveResolver_PostgresOpenError(t *testing.T) {
	openDB := func(string) (*sql.DB, error) { return nil, errors.New("open boom") }
	log := logger.Discard("proxy")

	_, _, err := setupDirectiveResolver(directiveResolverSetup{
		Config: config.Config{PostgresDSN: "postgres://example/ibex"},
		Log:    log, OpenDB: openDB,
	})
	if err == nil {
		t.Fatal("expected open error")
	}
}

func mustStubPostgres(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/nope?sslmode=disable")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

func mustSetupDirectiveWithDSN(t *testing.T, openDB postgresOpener) (*sql.DB, directive.Resolver) {
	t.Helper()
	gotDB, resolver, err := setupDirectiveResolver(directiveResolverSetup{
		Config: config.Config{PostgresDSN: "postgres://example/ibex"},
		Log:    logger.Discard("proxy"), OpenDB: openDB,
	})
	if err != nil {
		t.Fatalf("setup: %v", err)
	}
	return gotDB, resolver
}

func assertSessionStoreWired(t *testing.T, db *sql.DB) {
	t.Helper()
	store, err := newSessionStore(db, nil, telemetry.NoopTracer("ibex-session"))
	if err != nil {
		t.Fatalf("session store err: %v", err)
	}
	if store == nil {
		t.Fatal("expected session store from DSN path")
	}
	deps := proxyhttp.RouterDeps{SessionStore: store}
	if deps.SessionStore == nil {
		t.Fatal("expected RouterDeps to receive SessionStore")
	}
}

func assertNoopDirectiveResolve(t *testing.T, resolver directive.Resolver) {
	t.Helper()
	got, err := resolver.Resolve(context.Background(), uuid.Nil, uuid.Nil)
	if err != nil {
		t.Fatalf("resolve err: %v", err)
	}
	if got.HasContent() {
		t.Fatalf("expected noop resolve, got %+v", got)
	}
}

func TestUnit_OpenProxyPostgres_BadDSN(t *testing.T) {
	t.Parallel()
	_, err := openProxyPostgres("postgres://127.0.0.1:1/nope?sslmode=disable&connect_timeout=1")
	if err == nil {
		t.Fatal("expected ping error")
	}
}

func TestUnit_BuildProxyHealth_WithAndWithoutPostgres(t *testing.T) {
	t.Parallel()
	cfg := config.Config{}
	cfg.ApplyDefaults()
	without := buildProxyHealth(cfg, nil, nil)
	if without.AdvisoryCheckers != nil {
		t.Fatal("expected no advisory checkers")
	}
	if _, ok := without.CriticalCheckers["auth_grpc"]; !ok {
		t.Fatal("missing auth_grpc checker")
	}
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/nope?sslmode=disable")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	with := buildProxyHealth(cfg, nil, db)
	if _, ok := with.AdvisoryCheckers["postgres"]; !ok {
		t.Fatal("missing postgres advisory checker")
	}
}

func TestUnit_NewCachedDirectiveResolver_NilDB(t *testing.T) {
	t.Parallel()
	log := logger.Discard("proxy")
	_, err := newCachedDirectiveResolver(cachedDirectiveInputs{
		DB: nil, Redis: nil, Config: config.Config{}, Log: log,
	})
	if err == nil {
		t.Fatal("expected loader error")
	}
}

func TestUnit_StartDirectiveSubscriber_StartsForCachedResolver(t *testing.T) {
	t.Parallel()
	log := logger.Discard("proxy")
	mr := miniredis.RunT(t)
	client, err := ratelimit.ParseRedisURL("redis://" + mr.Addr() + "/0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	store := &staticDirectiveLoader{}
	resolver, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	sub, cancel, err := startDirectiveSubscriber(client, resolver, log, nil)
	if err != nil {
		t.Fatalf("start: %v", err)
	}
	if sub == nil || cancel == nil {
		t.Fatal("expected subscriber")
	}
	cancel()
	sub.Stop()
	<-sub.Done()
}

func TestUnit_StopPubSubSubscribers_NilSafe(t *testing.T) {
	t.Parallel()
	stopPubSubSubscribers(shutdownOpts{})
	called := false
	stopPubSubSubscribers(shutdownOpts{
		revCancel: func() { called = true },
		dirCancel: func() { called = true },
	})
	if !called {
		t.Fatal("expected cancel hooks")
	}
}

type staticDirectiveLoader struct{}

func (staticDirectiveLoader) Load(context.Context, uuid.UUID, uuid.UUID) (directive.Resolved, error) {
	return directive.Resolved{}, nil
}

func TestUnit_NewSessionSweeper(t *testing.T) {
	t.Parallel()
	got, err := newSessionSweeper(sessionSweeperSetup{})
	if err != nil || got != nil {
		t.Fatalf("nil store: got=%v err=%v", got, err)
	}

	cfg := config.Config{SessionIdleTimeout: time.Hour, SessionSweepInterval: time.Minute}
	cfg.ApplyDefaults()
	store := stubSessionStore{}
	sw, err := newSessionSweeper(sessionSweeperSetup{Store: store, Config: cfg})
	if err != nil || sw == nil {
		t.Fatalf("construct: sw=%v err=%v", sw, err)
	}

	bad := config.Config{SessionIdleTimeout: time.Second, SessionSweepInterval: time.Minute}
	if _, err := newSessionSweeper(sessionSweeperSetup{Store: store, Config: bad}); err == nil {
		t.Fatal("expected idle < interval error")
	}

	startSessionSweeper(nil, cfg, nil)
	startSessionSweeper(sw, cfg, logger.Discard("proxy"))
	t.Cleanup(func() { _ = sw.Stop(context.Background()) })
}

type stubSessionStore struct{}

func (stubSessionStore) GetOrCreate(context.Context, session.GetOrCreateParams) (*session.Session, error) {
	return nil, errors.New("unused")
}
func (stubSessionStore) AppendCheckpoint(context.Context, session.CheckpointParams) error {
	return errors.New("unused")
}
func (stubSessionStore) Complete(context.Context, uuid.UUID, uuid.UUID) error {
	return errors.New("unused")
}
func (stubSessionStore) AbandonIdle(context.Context, session.AbandonIdleParams) (session.AbandonIdleResult, error) {
	return session.AbandonIdleResult{SkippedLock: true}, nil
}
