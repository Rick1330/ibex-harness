package bootstrap

import (
	"context"
	"log/slog"
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

// Run loads config, wires dependencies, and serves until shutdown.
func Run(args []string) int {
	return runBootstrap(args, nil)
}

// RunWithSignalChan is used by tests to inject a signal channel.
func RunWithSignalChan(args []string, signalCh chan os.Signal) int {
	return runBootstrap(args, signalCh)
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
		checkpointPool: core.checkpointPool, sessionSweeper: core.sessionSweeper,
		traceWriter: core.traceWriter,
		signalCh:    signalCh,
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
