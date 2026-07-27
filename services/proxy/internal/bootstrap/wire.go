package bootstrap

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessionsweeper"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

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
	sessionSweeper *sessionsweeper.Sweeper
	traceWriter    *ibexch.Writer
}

func setupProxyCore(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
	tracer trace.Tracer,
) (*proxyCore, error) {
	assembled, err := assembleProxyCore(cfg, log, reg, tracer)
	if err != nil {
		return nil, err
	}
	revSub, revCancel, err := startRevocationSubscriber(
		assembled.redisClient, assembled.validator, log, reg,
	)
	if err != nil {
		return nil, fmt.Errorf("revocation subscriber: %w", err)
	}
	dirSub, dirCancel, err := startDirectiveSubscriber(
		assembled.redisClient, assembled.directiveResolver, log, reg,
	)
	if err != nil {
		return nil, fmt.Errorf("directive subscriber: %w", err)
	}
	startSessionSweeper(assembled.sessionSweeper, cfg, log)
	return finishProxyCore(proxyCoreParts{
		assembled: assembled,
		revSub:    revSub, revCancel: revCancel,
		dirSub: dirSub, dirCancel: dirCancel,
	}), nil
}

type proxyCoreParts struct {
	assembled assembledProxyCore
	revSub    *revocation.Subscriber
	revCancel context.CancelFunc
	dirSub    *directive.Subscriber
	dirCancel context.CancelFunc
}

func finishProxyCore(parts proxyCoreParts) *proxyCore {
	return &proxyCore{
		server: parts.assembled.server, grpcConn: parts.assembled.grpcConn,
		redisClient: parts.assembled.redisClient, pgDB: parts.assembled.pgDB,
		revSub: parts.revSub, revCancel: parts.revCancel,
		dirSub: parts.dirSub, dirCancel: parts.dirCancel,
		checkpointPool: parts.assembled.checkpointPool,
		sessionSweeper: parts.assembled.sessionSweeper,
		traceWriter:    parts.assembled.traceWriter,
	}
}

type assembledProxyCore struct {
	server            *http.Server
	grpcConn          *grpc.ClientConn
	redisClient       redis.UniversalClient
	pgDB              *sql.DB
	validator         auth.TokenValidator
	directiveResolver directive.Resolver
	checkpointPool    *asyncpool.Pool
	sessionSweeper    *sessionsweeper.Sweeper
	traceWriter       *ibexch.Writer
}

func assembleProxyCore(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
	tracer trace.Tracer,
) (assembledProxyCore, error) {
	redisClient, limiter, err := setupRateLimiter(cfg, log)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("rate limiter: %w", err)
	}
	validator, agentVerifier, authClient, grpcConn, err := setupAuthClients(cfg, log, reg)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("auth clients: %w", err)
	}
	pgDB, directiveResolver, err := setupDirectiveResolver(directiveResolverSetup{
		Config: cfg, Redis: redisClient, Log: log, Reg: reg, OpenDB: openProxyPostgres,
	})
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("directive resolver: %w", err)
	}
	sessionStack, err := setupSessionStack(sessionStackSetup{
		DB: pgDB, Redis: redisClient, Config: cfg, Log: log, Reg: reg, Tracer: tracer,
	})
	if err != nil {
		return assembledProxyCore{}, err
	}
	providerReg, err := providerRegistryInit(cfg, log, tracer, reg)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("provider registry: %w", err)
	}
	traceWriter := optionalTraceWriter(cfg, log, reg)
	deps := proxyhttp.RouterDeps{
		Config: cfg, Logger: log, Metrics: reg, Tracer: tracer,
		Validator: validator, AgentVerifier: agentVerifier, Limiter: limiter,
		DirectiveResolver: directiveResolver, SessionStore: sessionStack.store,
		SessionCache: sessionStack.cache, CheckpointPool: sessionStack.pool,
		GetOrCreateTimeout: cfg.SessionGetOrCreateTO,
		Health:             buildProxyHealth(cfg, authClient, pgDB),
		ProviderRegistry:   providerReg,
		IdempotencyStore:   newIdempotencyStore(redisClient, cfg),
	}
	assignTraceWriter(&deps, traceWriter)
	server, err := newHTTPServer(deps)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("http router: %w", err)
	}
	return assembledProxyCore{
		server: server, grpcConn: grpcConn, redisClient: redisClient, pgDB: pgDB,
		validator: validator, directiveResolver: directiveResolver,
		checkpointPool: sessionStack.pool, sessionSweeper: sessionStack.sweeper,
		traceWriter: traceWriter,
	}, nil
}

// assignTraceWriter sets TraceWriter only when w is non-nil so a nil *Writer
// is not boxed into a non-nil interface value.
func assignTraceWriter(deps *proxyhttp.RouterDeps, w *ibexch.Writer) {
	if w == nil {
		return
	}
	deps.TraceWriter = w
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

func newHTTPServer(deps proxyhttp.RouterDeps) (*http.Server, error) {
	handler, err := proxyhttp.NewRouter(deps)
	if err != nil {
		return nil, err
	}
	return &http.Server{
		Addr:              ":" + deps.Config.Port,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}, nil
}
