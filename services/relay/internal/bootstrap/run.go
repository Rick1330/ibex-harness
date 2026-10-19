package bootstrap

import (
	"context"
	"os"
	"sync/atomic"

	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
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

	reg := ibexmetrics.NewRelay(cfg.ServiceName)
	rt, err := openRuntime(ctx, cfg, reg)
	if err != nil {
		log.ErrorCtx(ctx, "relay runtime setup failed", "error", err)
		return 1
	}

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
		relay:      rt.relay,
		metrics:    reg,
		rt:         rt,
		signalCh:   signalCh,
	})
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
