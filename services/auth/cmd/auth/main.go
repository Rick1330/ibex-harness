package main

import (
	"context"
	"database/sql"
	"fmt"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	grpcserver "github.com/Rick1330/ibex-harness/services/auth/internal/grpc"
	authhttp "github.com/Rick1330/ibex-harness/services/auth/internal/http"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	return runBootstrap(args, nil)
}

type bootstrapResources struct {
	db          *sql.DB
	providers   *telemetry.Providers
	redisClient redis.UniversalClient
	grpcSrv     *grpc.Server
	grpcLis     net.Listener
}

func (r *bootstrapResources) cleanup() {
	if r.grpcLis != nil {
		_ = r.grpcLis.Close()
	}
	if r.grpcSrv != nil {
		r.grpcSrv.Stop()
	}
	if r.redisClient != nil {
		_ = r.redisClient.Close()
	}
	if r.providers != nil {
		_ = r.providers.Shutdown(context.Background())
	}
	if r.db != nil {
		_ = r.db.Close()
	}
}

func runBootstrap(_ []string, signalCh chan os.Signal) int {
	cfg, log, ok := loadAuthBootstrap()
	if !ok {
		return 1
	}

	res := &bootstrapResources{}
	handoff := false
	defer func() {
		if !handoff {
			res.cleanup()
		}
	}()

	runtime, err := initAuthRuntime(cfg, log, res)
	if err != nil {
		return 1
	}

	httpServer := newAuthHTTPServer(authHTTPServerOpts{
		Config: cfg, Log: log, Reg: runtime.reg, Tracer: runtime.tracer, DB: res.db,
	})

	handoff = true
	return runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, providers: res.providers, grpcSrv: res.grpcSrv, grpcLis: res.grpcLis,
		httpServer: httpServer, db: res.db, redisClient: runtime.deps.redisClient,
		tokenSvc: runtime.deps.tokenSvc, signalCh: signalCh,
	})
}

type authRuntime struct {
	reg    *ibexmetrics.AuthRegistry
	deps   authServiceDeps
	tracer trace.Tracer
}

func initAuthRuntime(cfg config.Config, log *logger.Logger, res *bootstrapResources) (authRuntime, error) {
	db, err := openAuthPostgres(cfg)
	if err != nil {
		log.ErrorCtx(context.Background(), "postgres open failed", "error", err)
		return authRuntime{}, err
	}
	res.db = db

	reg := ibexmetrics.NewAuth(ibexmetrics.AuthConfig{ServiceName: cfg.ServiceName, DB: db})
	deps, err := initAuthServices(cfg, db, log, reg)
	if err != nil {
		log.ErrorCtx(context.Background(), "auth services init failed", "error", err)
		return authRuntime{}, err
	}
	res.redisClient = deps.redisClient

	providers, tracer, err := initAuthTelemetry(cfg, log)
	if err != nil {
		return authRuntime{}, err
	}
	res.providers = providers

	grpcSrv, grpcLis, err := startAuthGRPC(cfg, deps, reg)
	if err != nil {
		log.ErrorCtx(context.Background(), "grpc startup failed", "error", err)
		return authRuntime{}, err
	}
	res.grpcSrv, res.grpcLis = grpcSrv, grpcLis

	return authRuntime{reg: reg, deps: deps, tracer: tracer}, nil
}

func loadAuthBootstrap() (config.Config, *logger.Logger, bool) {
	cfg, err := config.Load()
	if err != nil {
		logger.BootstrapError("invalid configuration", err)
		return config.Config{}, nil, false
	}
	log, err := logger.New(logger.Config{Service: cfg.ServiceName, Level: cfg.LogLevel})
	if err != nil {
		logger.BootstrapError("logger init failed", err)
		return config.Config{}, nil, false
	}
	return cfg, log, true
}

type authServiceDeps struct {
	validator       *token.Validator
	tokenSvc        *service.TokenService
	agentsRepo      *repository.AgentsRepository
	redisClient     redis.UniversalClient
	validateLimiter ratelimit.KeyedLimiter
	log             *logger.Logger
}

func initAuthServices(
	cfg config.Config,
	db *sql.DB,
	log *logger.Logger,
	reg *ibexmetrics.AuthRegistry,
) (authServiceDeps, error) {
	repo, err := repository.NewTokensRepository(db, reg)
	if err != nil {
		return authServiceDeps{}, err
	}
	agentsRepo := repository.NewAgentsRepository(db, reg)
	usersRepo := repository.NewUsersRepository(db, reg)
	lookup, err := token.NewRepoLookup(repo)
	if err != nil {
		return authServiceDeps{}, err
	}
	validator, err := token.NewValidator(lookup, cfg.Argon2)
	if err != nil {
		return authServiceDeps{}, err
	}

	redisClient, publisher, err := setupRevocationPublisher(cfg, log, reg)
	if err != nil {
		return authServiceDeps{}, err
	}
	validateLimiter, err := newValidateTokenLimiter(cfg, redisClient, log)
	if err != nil {
		return authServiceDeps{}, err
	}
	subjects, err := service.NewRepoTokenSubjects(agentsRepo, service.UsersFinder(usersRepo))
	if err != nil {
		return authServiceDeps{}, err
	}
	tokenSvc := service.NewTokenService(repo, cfg.Argon2, log, publisher).WithSubjectLookup(subjects)
	return authServiceDeps{
		validator: validator, tokenSvc: tokenSvc, agentsRepo: agentsRepo,
		redisClient: redisClient, validateLimiter: validateLimiter, log: log,
	}, nil
}

func newValidateTokenLimiter(
	cfg config.Config,
	redisClient redis.UniversalClient,
	log *logger.Logger,
) (ratelimit.KeyedLimiter, error) {
	if redisClient == nil {
		log.WarnCtx(context.Background(),
			"ValidateToken rate limit disabled; REDIS_URL empty (private-network assumption)")
		return ratelimit.NoopKeyed(), nil
	}
	limiter, err := ratelimit.NewRedisKeyed(redisClient, ratelimit.RedisKeyedConfig{
		DefaultRPM: cfg.ValidateTokenRPM,
		KeyPrefix:  "ratelimit:auth:validate",
	})
	if err != nil {
		return nil, fmt.Errorf("ValidateToken rate limiter: %w", err)
	}
	log.InfoCtx(context.Background(), "ValidateToken rate limit configured",
		"rpm", cfg.ValidateTokenRPM, "key_prefix", "ratelimit:auth:validate")
	return limiter, nil
}

func newAuthGRPCServer(deps authServiceDeps, reg *ibexmetrics.AuthRegistry) (*grpc.Server, error) {
	grpcSrv := grpc.NewServer(
		grpc.ChainUnaryInterceptor(
			grpcserver.MetricsUnaryInterceptor(reg),
			grpcserver.ValidateTokenRateLimitInterceptor(grpcserver.ValidateRateLimitOpts{
				Limiter: deps.validateLimiter,
				Log:     deps.log,
			}),
			grpcserver.AuthzUnaryInterceptor(deps.validator),
		),
	)
	if err := registerAuthGRPC(grpcSrv, deps, reg); err != nil {
		return nil, fmt.Errorf("register auth grpc: %w", err)
	}
	return grpcSrv, nil
}

func setupRevocationPublisher(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.AuthRegistry,
) (redis.UniversalClient, revocation.Publisher, error) {
	if cfg.RedisURL == "" {
		log.InfoCtx(context.Background(), "revocation publisher disabled; REDIS_URL empty")
		return nil, revocation.NoopPublisher{}, nil
	}
	client, err := ratelimit.ParseRedisURL(cfg.RedisURL)
	if err != nil {
		return nil, nil, fmt.Errorf("redis client init: %w", err)
	}
	pub, err := revocation.NewRedisPublisher(client, log, reg)
	if err != nil {
		_ = client.Close()
		return nil, nil, err
	}
	log.InfoCtx(context.Background(), "revocation publisher configured", "channel", revocation.Channel)
	return client, pub, nil
}

func configurePostgresPool(db *sql.DB) {
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)
}

func startAuthGRPC(
	cfg config.Config,
	deps authServiceDeps,
	reg *ibexmetrics.AuthRegistry,
) (*grpc.Server, net.Listener, error) {
	grpcSrv, err := newAuthGRPCServer(deps, reg)
	if err != nil {
		return nil, nil, fmt.Errorf("auth grpc server: %w", err)
	}
	addr := config.ListenAddress(cfg.GRPCPort)
	lis, err := net.Listen("tcp", addr)
	if err != nil {
		return nil, nil, fmt.Errorf("listen auth grpc addr=%s: %w", addr, err)
	}
	return grpcSrv, lis, nil
}

func initAuthTelemetry(cfg config.Config, log *logger.Logger) (*telemetry.Providers, trace.Tracer, error) {
	providers, tracer, err := telemetry.InitTracer(context.Background(), cfg.Telemetry, "ibex-auth")
	if err != nil {
		log.ErrorCtx(context.Background(), "telemetry init failed", "error", err)
		return nil, nil, err
	}
	return providers, tracer, nil
}

func openAuthPostgres(cfg config.Config) (*sql.DB, error) {
	db, err := sql.Open("postgres", cfg.PostgresDSN)
	if err != nil {
		return nil, err
	}
	configurePostgresPool(db)
	return db, nil
}

type authHTTPServerOpts struct {
	Config config.Config
	Log    *logger.Logger
	Reg    *ibexmetrics.AuthRegistry
	Tracer trace.Tracer
	DB     *sql.DB
}

func newAuthHTTPServer(opts authHTTPServerOpts) *http.Server {
	healthSrv := &healthcheck.Server{
		CriticalCheckers: map[string]healthcheck.Checker{
			"postgres": healthcheck.PostgresSelect1(opts.DB),
			"grpc":     healthcheck.TCPReachable(config.ListenAddress(opts.Config.GRPCPort)),
		},
	}
	return &http.Server{
		Addr:              config.ListenAddress(opts.Config.Port),
		Handler:           authhttp.NewRouter(opts.Log, opts.Reg, opts.Tracer, healthSrv),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      120 * time.Second,
		IdleTimeout:       90 * time.Second,
	}
}

func registerAuthGRPC(grpcSrv *grpc.Server, deps authServiceDeps, reg *ibexmetrics.AuthRegistry) error {
	agentSvc, err := service.NewAgentService(deps.agentsRepo)
	if err != nil {
		return fmt.Errorf("agent service: %w", err)
	}
	srv, err := grpcserver.NewServer(grpcserver.ServerDeps{
		Validator:    deps.validator,
		TokenService: deps.tokenSvc,
		AgentService: agentSvc,
		Metrics:      reg,
		Log:          deps.log,
	})
	if err != nil {
		return fmt.Errorf("grpc auth service: %w", err)
	}
	authv1.RegisterAuthServiceServer(grpcSrv, srv)
	return nil
}
