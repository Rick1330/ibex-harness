package bootstrap

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/extractionbuffer"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessionsweeper"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/trace"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

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

type sessionHotPath struct {
	cache      *sessioncache.Cache
	pool       *asyncpool.Pool
	turnBuffer *extractionbuffer.Buffer
}

type sessionStackSetup struct {
	DB     *sql.DB
	Redis  redis.UniversalClient
	Config config.Config
	Log    *logger.Logger
	Reg    *ibexmetrics.ProxyRegistry
	Tracer trace.Tracer
}

type sessionStack struct {
	store      session.Store
	cache      *sessioncache.Cache
	pool       *asyncpool.Pool
	turnBuffer *extractionbuffer.Buffer
	sweeper    *sessionsweeper.Sweeper
}

func setupSessionStack(in sessionStackSetup) (sessionStack, error) {
	store, err := newSessionStore(in.DB, in.Reg, in.Tracer)
	if err != nil {
		return sessionStack{}, fmt.Errorf("session store: %w", err)
	}
	parts, err := setupSessionHotPath(in.Redis, in.Config, in.Reg)
	if err != nil {
		return sessionStack{}, err
	}
	sweeper, err := newSessionSweeper(sessionSweeperSetup{
		Store: store, Cache: parts.cache, Config: in.Config, Log: in.Log, Reg: in.Reg,
	})
	if err != nil {
		return sessionStack{}, err
	}
	return sessionStack{
		store: store, cache: parts.cache, pool: parts.pool,
		turnBuffer: parts.turnBuffer, sweeper: sweeper,
	}, nil
}

func setupSessionHotPath(
	redisClient redis.UniversalClient,
	cfg config.Config,
	reg *ibexmetrics.ProxyRegistry,
) (sessionHotPath, error) {
	cache, err := newSessionCache(redisClient, cfg)
	if err != nil {
		return sessionHotPath{}, fmt.Errorf("session cache: %w", err)
	}
	pool, err := newCheckpointPool(cfg, reg)
	if err != nil {
		return sessionHotPath{}, fmt.Errorf("checkpoint pool: %w", err)
	}
	turnBuffer, err := newExtractionTurnBuffer(redisClient, cfg)
	if err != nil {
		return sessionHotPath{}, fmt.Errorf("extraction turn buffer: %w", err)
	}
	return sessionHotPath{cache: cache, pool: pool, turnBuffer: turnBuffer}, nil
}

func newExtractionTurnBuffer(redisClient redis.UniversalClient, cfg config.Config) (*extractionbuffer.Buffer, error) {
	if redisClient == nil {
		return nil, nil
	}
	ttl := cfg.ExtractionTurnsTTL
	if ttl <= 0 {
		ttl = cfg.SessionIdleTimeout
	}
	return extractionbuffer.New(redisClient, ttl)
}

type sessionSweeperSetup struct {
	Store  session.Store
	Cache  *sessioncache.Cache
	Config config.Config
	Log    *logger.Logger
	Reg    *ibexmetrics.ProxyRegistry
}

func newSessionSweeper(in sessionSweeperSetup) (*sessionsweeper.Sweeper, error) {
	if in.Store == nil {
		return nil, nil
	}
	var metrics sessionsweeper.Metrics
	if in.Reg != nil {
		metrics = in.Reg
	}
	sw, err := sessionsweeper.New(sessionsweeper.Config{
		IdleTimeout: in.Config.SessionIdleTimeout,
		Interval:    in.Config.SessionSweepInterval,
	}, sessionsweeper.Deps{
		Store: in.Store, Cache: in.Cache, Log: in.Log, Metrics: metrics,
	})
	if err != nil {
		return nil, fmt.Errorf("session sweeper: %w", err)
	}
	return sw, nil
}

func startSessionSweeper(sw *sessionsweeper.Sweeper, cfg config.Config, log *logger.Logger) {
	if sw == nil {
		return
	}
	sw.Start()
	if log == nil {
		return
	}
	log.InfoCtx(context.Background(), "session idle sweeper started",
		"idle_timeout", cfg.SessionIdleTimeout.String(),
		"interval", cfg.SessionSweepInterval.String(),
	)
}

const (
	pgMaxOpenConns    = 10
	pgMaxIdleConns    = 5
	pgConnMaxLifetime = time.Hour
	pgPingTimeout     = 5 * time.Second
)

func openProxyPostgres(dsn string) (*sql.DB, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("postgres open: %w", err)
	}
	db.SetMaxOpenConns(pgMaxOpenConns)
	db.SetMaxIdleConns(pgMaxIdleConns)
	db.SetConnMaxLifetime(pgConnMaxLifetime)
	pingCtx, cancel := context.WithTimeout(context.Background(), pgPingTimeout)
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
	if log != nil {
		log.InfoCtx(context.Background(), "directive subscriber started", "pattern", directive.ChannelPattern)
	}
	return sub, cancel, nil
}

// startRateLimitConfigSubscriber reloads DB RPM overrides via pub/sub + 30s poll.
// Skips (env-only limiter) when Redis, Postgres, or a HierarchicalLimiter is missing.
func startRateLimitConfigSubscriber(
	redisClient redis.UniversalClient,
	pgDB *sql.DB,
	limiter ratelimit.Limiter,
	log *logger.Logger,
) (*ratelimit.ConfigSubscriber, context.CancelFunc, error) {
	if skip, reason := rateLimitWatcherSkipReason(redisClient, pgDB, limiter); skip {
		if log != nil {
			log.InfoCtx(context.Background(), "rate-limit config watcher skipped; env defaults only",
				"reason", reason)
		}
		return nil, nil, nil
	}
	hier, _ := ratelimit.AsHierarchical(limiter)
	store, err := ratelimit.NewConfigStore(pgDB)
	if err != nil {
		return nil, nil, err
	}
	sub, err := ratelimit.NewConfigSubscriber(ratelimit.ConfigSubscriberDeps{
		Client: redisClient, Store: store, Applier: hier, Log: log,
		PollEvery: ratelimit.DefaultConfigPollInterval,
	})
	if err != nil {
		return nil, nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	go sub.Run(ctx)
	if log != nil {
		log.InfoCtx(context.Background(), "rate-limit config subscriber started",
			"pattern", ratelimit.ChannelPattern,
			"poll", ratelimit.DefaultConfigPollInterval.String())
	}
	return sub, cancel, nil
}

func modelPolicyMetrics(reg *ibexmetrics.ProxyRegistry) modelpolicy.Metrics {
	if reg != nil {
		return reg
	}
	return modelpolicy.NoopMetrics{}
}

func buildModelPolicyRuntime(
	pgDB *sql.DB,
	base *provider.Registry,
	log *logger.Logger,
	metrics *ibexmetrics.ProxyRegistry,
) (*modelpolicy.Cache, proxyhttp.ProviderResolver, modelpolicy.AgentDefaultLoader, error) {
	if pgDB == nil || base == nil {
		reason := "POSTGRES_DSN unset or db handle nil"
		if base == nil {
			reason = "provider registry nil"
		}
		warnModelPolicyPassthrough(log, metrics, reason)
		return nil, modelpolicy.PassthroughRegistry{Base: base}, modelpolicy.NoopAgentDefaults{}, nil
	}
	m := modelPolicyMetrics(metrics)
	cache, reg, err := newOrgPolicyStack(pgDB, base, m)
	if err != nil {
		return nil, nil, nil, err
	}
	agentDefaults, err := newCachedAgentDefaults(pgDB)
	if err != nil {
		return nil, nil, nil, err
	}
	if metrics != nil {
		metrics.SetModelPolicyEnabled(true)
	}
	if log != nil {
		log.InfoCtx(context.Background(), "model policy org-aware registry enabled")
	}
	return cache, reg, agentDefaults, nil
}

func warnModelPolicyPassthrough(log *logger.Logger, metrics *ibexmetrics.ProxyRegistry, reason string) {
	if metrics != nil {
		metrics.SetModelPolicyEnabled(false)
	}
	if log == nil {
		return
	}
	log.WarnCtx(context.Background(),
		"model policy passthrough: org model policies disabled; every model allowed for every org",
		"reason", reason,
	)
}

func newOrgPolicyStack(
	pgDB *sql.DB,
	base *provider.Registry,
	m modelpolicy.Metrics,
) (*modelpolicy.Cache, *modelpolicy.OrgAwareRegistry, error) {
	store, err := modelpolicy.NewStore(pgDB)
	if err != nil {
		return nil, nil, err
	}
	cache, err := modelpolicy.NewCache(store, modelpolicy.Config{}, m)
	if err != nil {
		return nil, nil, err
	}
	reg, err := modelpolicy.NewOrgAwareRegistry(base, cache, m)
	if err != nil {
		return nil, nil, err
	}
	return cache, reg, nil
}

func newCachedAgentDefaults(pgDB *sql.DB) (modelpolicy.AgentDefaultLoader, error) {
	agentStore, err := modelpolicy.NewAgentStore(pgDB)
	if err != nil {
		return nil, err
	}
	return modelpolicy.NewCachingAgentDefaults(agentStore, modelpolicy.Config{})
}

func startModelPolicySubscriber(
	redisClient redis.UniversalClient,
	cache *modelpolicy.Cache,
	log *logger.Logger,
	metrics *ibexmetrics.ProxyRegistry,
) (*modelpolicy.Subscriber, context.CancelFunc, error) {
	if redisClient == nil || cache == nil {
		return nil, nil, nil
	}
	sub, err := modelpolicy.NewSubscriber(redisClient, cache, log, modelPolicyMetrics(metrics))
	if err != nil {
		return nil, nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	go sub.Run(ctx)
	if log != nil {
		log.InfoCtx(context.Background(), "model-policy subscriber started", "pattern", modelpolicy.ChannelPattern)
	}
	return sub, cancel, nil
}

func rateLimitWatcherSkipReason(
	redisClient redis.UniversalClient, pgDB *sql.DB, limiter ratelimit.Limiter,
) (skip bool, reason string) {
	if redisClient == nil {
		return true, "redis_missing"
	}
	if pgDB == nil {
		return true, "postgres_missing"
	}
	if _, ok := ratelimit.AsHierarchical(limiter); !ok {
		return true, "limiter_not_hierarchical"
	}
	return false, ""
}
