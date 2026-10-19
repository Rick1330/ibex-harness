package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"sync/atomic"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/services/relay/internal/config"
)

type shutdownOpts struct {
	cfg        config.Config
	log        *logger.Logger
	server     *http.Server
	draining   *atomic.Bool
	cancelLoop context.CancelFunc
	loopDone   <-chan struct{}
	relay      batchRelay
	metrics    *ibexmetrics.RelayRegistry
	rt         *runtime
	signalCh   chan os.Signal
}

func runWithShutdown(opts shutdownOpts) int {
	errCh := make(chan error, 1)
	go func() {
		opts.log.InfoCtx(context.Background(), "service starting", "addr", opts.server.Addr)
		if err := opts.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()

	var sd *shutdown.Coordinator
	if opts.signalCh != nil {
		sd = shutdown.NewWithSignalChan(opts.cfg.ShutdownTimeout, opts.log, opts.signalCh)
	} else {
		sd = shutdown.New(opts.cfg.ShutdownTimeout, opts.log)
	}
	registerRelayShutdownHooks(sd, opts)

	shutdownErrCh := make(chan error, 1)
	go func() {
		shutdownErrCh <- sd.Wait()
	}()

	return awaitRelayShutdown(opts, errCh, shutdownErrCh)
}

func awaitRelayShutdown(opts shutdownOpts, errCh, shutdownErrCh <-chan error) int {
	select {
	case err := <-errCh:
		if err != nil {
			opts.log.ErrorCtx(context.Background(), "server failed", "error", err)
			immediateRelayCleanup(opts)
			return 1
		}
		if err := <-shutdownErrCh; err != nil {
			return 1
		}
	case err := <-shutdownErrCh:
		if err != nil {
			return 1
		}
		if err := <-errCh; err != nil {
			opts.log.ErrorCtx(context.Background(), "server failed", "error", err)
			return 1
		}
	}
	opts.log.InfoCtx(context.Background(), "service stopped")
	return 0
}

func immediateRelayCleanup(opts shutdownOpts) {
	opts.cancelLoop()
	if err := closeRuntime(opts.rt); err != nil {
		opts.log.ErrorCtx(context.Background(), "immediate cleanup failed", "error", err)
	}
}

// registerRelayShutdownHooks orders teardown: flip draining and stop the loop,
// wait for the in-flight batch, release any claims we left in_flight, then
// close the HTTP surface and dependencies.
func registerRelayShutdownHooks(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(context.Context) error {
		opts.draining.Store(true)
		opts.cancelLoop()
		return nil
	})
	sd.Register(func(ctx context.Context) error {
		select {
		case <-opts.loopDone:
			return nil
		case <-ctx.Done():
			return fmt.Errorf("relay loop drain: %w", ctx.Err())
		}
	})
	sd.Register(func(ctx context.Context) error {
		recovered, err := opts.relay.RecoverInFlight(ctx, time.Nanosecond)
		if err != nil {
			return fmt.Errorf("release in-flight claims: %w", err)
		}
		if recovered > 0 {
			opts.metrics.AddRecovered(int(recovered))
			opts.log.InfoCtx(ctx, "released in-flight claims", "count", recovered)
		}
		return nil
	})
	sd.Register(func(ctx context.Context) error {
		return opts.server.Shutdown(ctx)
	})
	sd.Register(func(context.Context) error {
		return opts.rt.sink.Close()
	})
	sd.Register(func(context.Context) error {
		return opts.rt.db.Close()
	})
}
