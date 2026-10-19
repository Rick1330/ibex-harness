package bootstrap

import (
	"context"
	"os"
	"sync/atomic"

	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
)

const bootstrapServiceName = "ibex-relay"

// Run is the command-facing process lifecycle entrypoint; it returns the
// process exit code.
func Run(args []string) int {
	return runBootstrap(args, nil)
}

func runBootstrap(_ []string, signalCh chan os.Signal) int {
	cfg, log, err := loadRelayRuntime()
	if err != nil {
		return 1
	}
	ctx := context.Background()
	if !cfg.Enabled {
		log.InfoCtx(ctx, "relay disabled: IBEX_RELAY_ENABLED is false; daemon not started")
		return 0
	}

	providers, err := initRelayTelemetry(ctx, cfg, log)
	if err != nil {
		return 1
	}
	defer func() {
		if err := providers.Shutdown(context.Background()); err != nil {
			log.ErrorCtx(context.Background(), "telemetry shutdown failed", "error", err)
		}
	}()

	reg := ibexmetrics.NewRelay(cfg.ServiceName)
	rt, err := openRuntime(ctx, cfg, reg)
	if err != nil {
		log.ErrorCtx(ctx, "relay runtime setup failed", "error", err)
		return 1
	}
	return serveRelay(cfg, log, reg, rt, signalCh)
}

// serveRelay starts the poll loop and HTTP server, then blocks until shutdown.
func serveRelay(cfg config.Config, log *logger.Logger, reg *ibexmetrics.RelayRegistry, rt *runtime, signalCh chan os.Signal) int {
	draining := &atomic.Bool{}
	loopCtx, cancelLoop := context.WithCancel(context.Background())
	loopDone := make(chan struct{})
	go func() {
		defer close(loopDone)
		runLoop(loopCtx, loopDeps{relay: rt.relay, metrics: reg, log: log, cfg: cfg})
	}()

	server := newRelayHTTPServer(cfg.Port, rt, reg, draining)
	return runWithShutdown(shutdownOpts{
		cfg:        cfg,
		log:        log,
		server:     server,
		draining:   draining,
		cancelLoop: cancelLoop,
		loopDone:   loopDone,
		rt:         rt,
		signalCh:   signalCh,
	})
}

// initRelayTelemetry wires OTLP tracing so dependency spans are exported when
// configured; without an endpoint it installs a no-op exporter.
func initRelayTelemetry(ctx context.Context, cfg config.Config, log *logger.Logger) (*telemetry.Providers, error) {
	telemetryCfg, err := telemetry.ConfigFromEnv(cfg.ServiceName, cfg.Environment)
	if err != nil {
		log.ErrorCtx(ctx, "telemetry config failed", "error", err)
		return nil, err
	}
	providers, _, err := telemetry.InitTracer(ctx, telemetryCfg, bootstrapServiceName)
	if err != nil {
		log.ErrorCtx(ctx, "telemetry init failed", "error", err)
		return nil, err
	}
	return providers, nil
}

func loadRelayRuntime() (config.Config, *logger.Logger, error) {
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
