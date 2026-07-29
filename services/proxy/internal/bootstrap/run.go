package bootstrap

import (
	"context"
	"os"

	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"go.opentelemetry.io/otel/trace"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

type providerRegistryBuilder func(config.Config, *logger.Logger, trace.Tracer, *ibexmetrics.ProxyRegistry) (*provider.Registry, error)

type bootstrapDeps struct {
	buildProviderRegistry providerRegistryBuilder
}

const bootstrapServiceName = "ibex-proxy"

// Run is the command-facing process lifecycle entrypoint; it returns the process exit code.
func Run(args []string) int {
	return runBootstrap(args, nil, defaultBootstrapDeps())
}

func defaultBootstrapDeps() bootstrapDeps {
	return bootstrapDeps{buildProviderRegistry: buildProviderRegistry}
}

func (d bootstrapDeps) withDefaults() bootstrapDeps {
	if d.buildProviderRegistry == nil {
		d.buildProviderRegistry = buildProviderRegistry
	}
	return d
}

func runBootstrap(_ []string, signalCh chan os.Signal, deps bootstrapDeps) int {
	deps = deps.withDefaults()
	cfg, log, err := loadProxyRuntime()
	if err != nil {
		return 1
	}
	providers, tracer, err := telemetry.InitTracer(context.Background(), cfg.Telemetry, bootstrapServiceName)
	if err != nil {
		log.ErrorCtx(context.Background(), "telemetry init failed", "error", err)
		return 1
	}
	reg := ibexmetrics.NewProxy(cfg.ServiceName)
	core, err := setupProxyCore(setupProxyCoreInput{
		cfg:    cfg,
		log:    log,
		reg:    reg,
		tracer: tracer,
		deps:   deps,
	})
	if err != nil {
		log.ErrorCtx(context.Background(), "proxy core setup failed", "error", err)
		return 1
	}
	return runWithShutdown(shutdownOpts{
		cfg: cfg, logger: log, providers: providers, server: core.server,
		grpcConn: core.grpcConn, redisClient: core.redisClient, pgDB: core.pgDB,
		revSub: core.revSub, revCancel: core.revCancel,
		dirSub: core.dirSub, dirCancel: core.dirCancel,
		checkpointPool: core.checkpointPool, sessionSweeper: core.sessionSweeper,
		traceWriter: core.traceWriter,
		signalCh:    signalCh,
	})
}

func loadProxyRuntime() (config.Config, *logger.Logger, error) {
	cfg, err := config.Load()
	if err != nil {
		fallbackBootstrapLogger().ErrorCtx(context.Background(), "invalid configuration", "error", err)
		return config.Config{}, nil, err
	}
	log, err := logger.New(logger.Config{Service: cfg.ServiceName, Level: cfg.LogLevel})
	if err != nil {
		fallbackBootstrapLogger().ErrorCtx(context.Background(), "logger init failed", "error", err)
		return config.Config{}, nil, err
	}
	return cfg, log, nil
}

func fallbackBootstrapLogger() *logger.Logger {
	log, err := logger.New(logger.Config{Service: bootstrapServiceName, Writer: os.Stderr})
	if err == nil {
		return log
	}
	return logger.Discard(bootstrapServiceName)
}
