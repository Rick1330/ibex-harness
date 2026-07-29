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
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
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

const (
	httpReadHeaderTimeout = 5 * time.Second
	httpReadTimeout       = 30 * time.Second
	httpWriteTimeout      = 120 * time.Second
	httpIdleTimeout       = 90 * time.Second
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

type setupProxyCoreInput struct {
	cfg    config.Config
	log    *logger.Logger
	reg    *ibexmetrics.ProxyRegistry
	tracer trace.Tracer
	deps   bootstrapDeps
}

func setupProxyCore(in setupProxyCoreInput) (*proxyCore, error) {
	assembled, err := assembleProxyCore(assembleProxyCoreInput(in))
	if err != nil {
		return nil, err
	}
	revSub, revCancel, err := startRevocationSubscriber(
		assembled.redisClient, assembled.validator, in.log, in.reg,
	)
	if err != nil {
		return nil, fmt.Errorf("revocation subscriber: %w", err)
	}
	dirSub, dirCancel, err := startDirectiveSubscriber(
		assembled.redisClient, assembled.directiveResolver, in.log, in.reg,
	)
	if err != nil {
		stopRevocationOnFailure(revSub, revCancel)
		return nil, fmt.Errorf("directive subscriber: %w", err)
	}
	startSessionSweeper(assembled.sessionSweeper, in.cfg, in.log)
	return finishProxyCore(proxyCoreParts{
		assembled: assembled,
		revSub:    revSub, revCancel: revCancel,
		dirSub: dirSub, dirCancel: dirCancel,
	}), nil
}

func stopRevocationOnFailure(sub *revocation.Subscriber, cancel context.CancelFunc) {
	if cancel != nil {
		cancel()
	}
	if sub != nil {
		sub.Stop()
	}
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

type proxyInfra struct {
	redisClient       redis.UniversalClient
	limiter           ratelimit.Limiter
	auth              authClients
	pgDB              *sql.DB
	directiveResolver directive.Resolver
	sessionStack      sessionStack
}

type assembleProxyCoreInput setupProxyCoreInput

func assembleProxyCore(in assembleProxyCoreInput) (assembledProxyCore, error) {
	infra, err := assembleProxyInfra(in.cfg, in.log, in.reg, in.tracer)
	if err != nil {
		return assembledProxyCore{}, err
	}
	return finishAssembledCore(finishAssembledCoreInput{
		cfg:    in.cfg,
		log:    in.log,
		reg:    in.reg,
		tracer: in.tracer,
		infra:  infra,
		deps:   in.deps,
	})
}

func assembleProxyInfra(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
	tracer trace.Tracer,
) (proxyInfra, error) {
	redisClient, limiter, err := setupRateLimiter(cfg, log)
	if err != nil {
		return proxyInfra{}, fmt.Errorf("rate limiter: %w", err)
	}
	authBundle, err := setupAuthClients(cfg, log, reg)
	if err != nil {
		return proxyInfra{}, fmt.Errorf("auth clients: %w", err)
	}
	pgDB, directiveResolver, err := setupDirectiveResolver(directiveResolverSetup{
		Config: cfg, Redis: redisClient, Log: log, Reg: reg, OpenDB: openProxyPostgres,
	})
	if err != nil {
		return proxyInfra{}, fmt.Errorf("directive resolver: %w", err)
	}
	stack, err := setupSessionStack(sessionStackSetup{
		DB: pgDB, Redis: redisClient, Config: cfg, Log: log, Reg: reg, Tracer: tracer,
	})
	if err != nil {
		return proxyInfra{}, fmt.Errorf("session stack: %w", err)
	}
	return proxyInfra{
		redisClient: redisClient, limiter: limiter, auth: authBundle,
		pgDB: pgDB, directiveResolver: directiveResolver, sessionStack: stack,
	}, nil
}

type finishAssembledCoreInput struct {
	cfg    config.Config
	log    *logger.Logger
	reg    *ibexmetrics.ProxyRegistry
	tracer trace.Tracer
	infra  proxyInfra
	deps   bootstrapDeps
}

func finishAssembledCore(in finishAssembledCoreInput) (assembledProxyCore, error) {
	providerReg, err := in.deps.buildProviderRegistry(in.cfg, in.log, in.tracer, in.reg)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("provider registry: %w", err)
	}
	idempStore, err := newIdempotencyStore(in.infra.redisClient, in.cfg)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("idempotency store: %w", err)
	}
	traceWriter := optionalTraceWriter(in.cfg, in.log, in.reg, ibexch.NewWriter)
	deps := proxyhttp.RouterDeps{
		Config: in.cfg, Logger: in.log, Metrics: in.reg, Tracer: in.tracer,
		Validator: in.infra.auth.validator, AgentVerifier: in.infra.auth.agentVerifier,
		Limiter: in.infra.limiter, DirectiveResolver: in.infra.directiveResolver,
		SessionStore: in.infra.sessionStack.store, SessionCache: in.infra.sessionStack.cache,
		CheckpointPool: in.infra.sessionStack.pool, GetOrCreateTimeout: in.cfg.SessionGetOrCreateTO,
		Health:           buildProxyHealth(in.cfg, in.infra.auth.client, in.infra.pgDB),
		ProviderRegistry: providerReg,
		IdempotencyStore: idempStore,
	}
	assignTraceWriter(&deps, traceWriter)
	server, err := newHTTPServer(deps)
	if err != nil {
		return assembledProxyCore{}, fmt.Errorf("http router: %w", err)
	}
	return assembledProxyCore{
		server: server, grpcConn: in.infra.auth.conn, redisClient: in.infra.redisClient, pgDB: in.infra.pgDB,
		validator: in.infra.auth.validator, directiveResolver: in.infra.directiveResolver,
		checkpointPool: in.infra.sessionStack.pool, sessionSweeper: in.infra.sessionStack.sweeper,
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
		ReadHeaderTimeout: httpReadHeaderTimeout,
		ReadTimeout:       httpReadTimeout,
		WriteTimeout:      httpWriteTimeout,
		IdleTimeout:       httpIdleTimeout,
	}, nil
}
