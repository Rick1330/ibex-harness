package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxygrpc "github.com/Rick1330/ibex-harness/services/proxy/internal/grpc"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	return runBootstrap(args, nil)
}

// providerRegistryInit is overridden in tests to simulate startup registry failures.
var providerRegistryInit = defaultProviderRegistryInit

func defaultProviderRegistryInit(cfg config.Config, log *logger.Logger, tracer trace.Tracer, reg *ibexmetrics.ProxyRegistry) (*provider.Registry, error) {
	return buildProviderRegistry(cfg, log, tracer, reg)
}

func runBootstrap(_ []string, signalCh chan os.Signal) int {
	cfg, log, err := loadProxyRuntime()
	if err != nil {
		return 1
	}
	providers, tracer, err := telemetry.InitTracer(context.Background(), cfg.Telemetry, "ibex-proxy")
	if err != nil {
		log.ErrorCtx(context.Background(), "telemetry init failed", "error", err)
		return 1
	}
	reg := ibexmetrics.NewProxy(cfg.ServiceName)
	core, err := setupProxyCore(cfg, log, reg, tracer)
	if err != nil {
		log.ErrorCtx(context.Background(), "proxy core setup failed", "error", err)
		return 1
	}
	return runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, providers: providers, server: core.server,
		grpcConn: core.grpcConn, redisClient: core.redisClient, pgDB: core.pgDB,
		revSub: core.revSub, revCancel: core.revCancel,
		dirSub: core.dirSub, dirCancel: core.dirCancel,
		checkpointPool: core.checkpointPool, serviceCancel: core.serviceCancel,
		signalCh: signalCh,
	})
}

func loadProxyRuntime() (config.Config, *logger.Logger, error) {
	cfg, err := config.Load()
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("invalid configuration", "error", err)
		return config.Config{}, nil, err
	}
	log, err := logger.New(logger.Config{Service: cfg.ServiceName, Level: cfg.LogLevel})
	if err != nil {
		slog.New(slog.NewJSONHandler(os.Stderr, nil)).Error("logger init failed", "error", err)
		return config.Config{}, nil, err
	}
	return cfg, log, nil
}

type proxyCore struct {
	server         *http.Server
	grpcConn       *grpc.ClientConn
	redisClient    redis.UniversalClient
	pgDB           *sql.DB
	revSub         *revocation.Subscriber
	revCancel      context.CancelFunc
	dirSub         *directive.Subscriber
	dirCancel      context.CancelFunc
	checkpointPool *asyncpool.Pool
	serviceCancel  context.CancelFunc
}

func setupProxyCore(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
	tracer trace.Tracer,
) (*proxyCore, error) {
	redisClient, limiter, err := setupRateLimiter(cfg, log)
	if err != nil {
		return nil, fmt.Errorf("rate limiter: %w", err)
	}
	validator, agentVerifier, authClient, grpcConn, err := setupAuthClients(cfg, log, reg)
	if err != nil {
		return nil, fmt.Errorf("auth clients: %w", err)
	}
	pgDB, directiveResolver, err := setupDirectiveResolver(directiveResolverSetup{
		Config: cfg, Redis: redisClient, Log: log, Reg: reg, OpenDB: openProxyPostgres,
	})
	if err != nil {
		return nil, fmt.Errorf("directive resolver: %w", err)
	}
	sessionStore, err := newSessionStore(pgDB, reg, tracer)
	if err != nil {
		return nil, fmt.Errorf("session store: %w", err)
	}
	sessionCache, err := newSessionCache(redisClient, cfg)
	if err != nil {
		return nil, fmt.Errorf("session cache: %w", err)
	}
	checkpointPool, err := newCheckpointPool(cfg, reg)
	if err != nil {
		return nil, fmt.Errorf("checkpoint pool: %w", err)
	}
	serviceCtx, serviceCancel := context.WithCancel(context.Background())
	healthSrv := buildProxyHealth(cfg, authClient, pgDB)
	providerReg, err := providerRegistryInit(cfg, log, tracer, reg)
	if err != nil {
		serviceCancel()
		return nil, fmt.Errorf("provider registry: %w", err)
	}
	server := newHTTPServer(proxyhttp.RouterDeps{
		Config: cfg, Logger: log, Metrics: reg, Tracer: tracer,
		Validator: validator, AgentVerifier: agentVerifier, Limiter: limiter,
		DirectiveResolver: directiveResolver, SessionStore: sessionStore,
		SessionCache: sessionCache, CheckpointPool: checkpointPool,
		ServiceCtx: serviceCtx, GetOrCreateTimeout: cfg.SessionGetOrCreateTO,
		Health: healthSrv, ProviderRegistry: providerReg,
	})
	revSub, revCancel, err := startRevocationSubscriber(redisClient, validator, log, reg)
	if err != nil {
		serviceCancel()
		return nil, fmt.Errorf("revocation subscriber: %w", err)
	}
	dirSub, dirCancel, err := startDirectiveSubscriber(redisClient, directiveResolver, log, reg)
	if err != nil {
		serviceCancel()
		return nil, fmt.Errorf("directive subscriber: %w", err)
	}
	return &proxyCore{
		server: server, grpcConn: grpcConn, redisClient: redisClient, pgDB: pgDB,
		revSub: revSub, revCancel: revCancel, dirSub: dirSub, dirCancel: dirCancel,
		checkpointPool: checkpointPool, serviceCancel: serviceCancel,
	}, nil
}

func buildProxyHealth(cfg config.Config, authClient authv1.AuthServiceClient, pgDB *sql.DB) *healthcheck.Server {
	healthSrv := &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"auth_grpc": healthcheck.AuthGRPC(authClient, cfg.AuthValidateTimeout),
			"redis":     healthcheck.RedisPing(cfg.RedisURL),
		},
	}
	if pgDB != nil {
		healthSrv.AdvisoryCheckers = map[string]healthcheck.Checker{
			"postgres": healthcheck.PostgresSelect1(pgDB),
		}
	}
	return healthSrv
}

type shutdownOpts struct {
	cfg            config.Config
	logger         *logger.Logger
	server         *http.Server
	providers      *telemetry.Providers
	grpcConn       *grpc.ClientConn
	redisClient    redis.UniversalClient
	pgDB           *sql.DB
	revSub         *revocation.Subscriber
	revCancel      context.CancelFunc
	dirSub         *directive.Subscriber
	dirCancel      context.CancelFunc
	checkpointPool *asyncpool.Pool
	serviceCancel  context.CancelFunc
	signalCh       chan os.Signal
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

type postgresOpener func(dsn string) (*sql.DB, error)

// directiveResolverSetup bundles Postgres/directive wiring inputs for setupDirectiveResolver.
type directiveResolverSetup struct {
	Config config.Config
	Redis  redis.UniversalClient
	Log    *logger.Logger
	Reg    *ibexmetrics.ProxyRegistry
	OpenDB postgresOpener
}

func setupDirectiveResolver(in directiveResolverSetup) (*sql.DB, directive.Resolver, error) {
	dsn := strings.TrimSpace(in.Config.PostgresDSN)
	if dsn == "" {
		in.Log.InfoCtx(context.Background(), "postgres unset; directive noop and session store disabled")
		return nil, directive.NoopResolver{}, nil
	}
	openDB := in.OpenDB
	if openDB == nil {
		openDB = openProxyPostgres
	}
	db, err := openDB(dsn)
	if err != nil {
		return nil, nil, err
	}
	if in.Redis == nil {
		in.Log.InfoCtx(context.Background(), "directive resolver noop; needs REDIS_URL with POSTGRES_DSN")
		return db, directive.NoopResolver{}, nil
	}
	resolver, err := newCachedDirectiveResolver(cachedDirectiveInputs{
		DB: db, Redis: in.Redis, Config: in.Config, Log: in.Log, Reg: in.Reg,
	})
	if err != nil {
		// Close best-effort: pool is unusable after construction failure.
		_ = db.Close()
		return nil, nil, fmt.Errorf("directive resolver: %w", err)
	}
	in.Log.InfoCtx(context.Background(), "directive resolver configured",
		"cache_ttl", in.Config.DirectiveCacheTTL.String())
	return db, resolver, nil
}

func newSessionStore(db *sql.DB, reg *ibexmetrics.ProxyRegistry, tracer trace.Tracer) (session.Store, error) {
	if db == nil {
		return nil, nil
	}
	var metrics session.Metrics = session.NoopMetrics{}
	if reg != nil {
		metrics = reg
	}
	return session.NewPostgresStore(session.PostgresStoreDeps{
		DB: db, Metrics: metrics, Tracer: tracer,
	})
}

func newSessionCache(redisClient redis.UniversalClient, cfg config.Config) (*sessioncache.Cache, error) {
	if redisClient == nil {
		return nil, nil
	}
	return sessioncache.New(redisClient, cfg.SessionCacheTTL)
}

func newCheckpointPool(cfg config.Config, reg *ibexmetrics.ProxyRegistry) (*asyncpool.Pool, error) {
	var depth asyncpool.DepthFunc
	if reg != nil {
		depth = reg.SetAsyncQueueDepth
	}
	return asyncpool.New(cfg.CheckpointWorkers, cfg.CheckpointQueue, depth)
}

func openProxyPostgres(dsn string) (*sql.DB, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("postgres open: %w", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(time.Hour)
	pingCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		_ = db.Close() // best-effort close after failed ping
		return nil, fmt.Errorf("postgres ping: %w", err)
	}
	return db, nil
}

type cachedDirectiveInputs struct {
	DB     *sql.DB
	Redis  redis.UniversalClient
	Config config.Config
	Log    *logger.Logger
	Reg    *ibexmetrics.ProxyRegistry
}

func newCachedDirectiveResolver(in cachedDirectiveInputs) (directive.Resolver, error) {
	loader, err := directive.NewPostgresStore(in.DB)
	if err != nil {
		return nil, fmt.Errorf("directive loader: %w", err)
	}
	var metrics directive.Metrics = directive.NoopMetrics{}
	if in.Reg != nil {
		metrics = in.Reg
	}
	resolver, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: in.Redis, Loader: loader,
		Config: directive.Config{CacheTTL: in.Config.DirectiveCacheTTL},
		Log:    in.Log, Metrics: metrics,
	})
	if err != nil {
		return nil, fmt.Errorf("directive cached resolver: %w", err)
	}
	return resolver, nil
}

func startDirectiveSubscriber(
	redisClient redis.UniversalClient,
	resolver directive.Resolver,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
) (*directive.Subscriber, context.CancelFunc, error) {
	if redisClient == nil {
		return nil, nil, nil
	}
	if _, ok := resolver.(*directive.CachedResolver); !ok {
		return nil, nil, nil
	}
	var metrics directive.Metrics = directive.NoopMetrics{}
	if reg != nil {
		metrics = reg
	}
	sub, err := directive.NewSubscriber(redisClient, resolver, log, metrics)
	if err != nil {
		return nil, nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	go sub.Run(ctx)
	log.InfoCtx(context.Background(), "directive subscriber started", "pattern", directive.ChannelPattern)
	return sub, cancel, nil
}

func newHTTPServer(deps proxyhttp.RouterDeps) *http.Server {
	return &http.Server{
		Addr:              ":" + deps.Config.Port,
		Handler:           proxyhttp.NewRouter(deps),
		ReadHeaderTimeout: 5 * time.Second,
	}
}

func runWithShutdown(opts shutdownOpts) int {
	defer stopPubSubSubscribers(opts)

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

func stopPubSubSubscribers(opts shutdownOpts) {
	if opts.revCancel != nil {
		opts.revCancel()
	}
	if opts.revSub != nil {
		opts.revSub.Stop()
	}
	if opts.dirCancel != nil {
		opts.dirCancel()
	}
	if opts.dirSub != nil {
		opts.dirSub.Stop()
	}
}

func registerShutdownHooks(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(opts.providers.Shutdown)
	sd.Register(func(ctx context.Context) error {
		return opts.server.Shutdown(ctx)
	})
	sd.Register(func(ctx context.Context) error {
		stopPubSubSubscribers(opts)
		return nil
	})
	sd.Register(func(ctx context.Context) error {
		if opts.checkpointPool != nil {
			return opts.checkpointPool.Shutdown(ctx)
		}
		return nil
	})
	sd.Register(func(ctx context.Context) error {
		if opts.serviceCancel != nil {
			opts.serviceCancel()
		}
		return nil
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
	sd.Register(func(ctx context.Context) error {
		if opts.pgDB != nil {
			return opts.pgDB.Close()
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
