package bootstrap

import (
	"context"
	"database/sql"
	"errors"
	"net/http"
	"os"
	"syscall"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessionsweeper"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

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
	sessionSweeper *sessionsweeper.Sweeper
	traceWriter    *ibexch.Writer
	signalCh       chan os.Signal
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

	return awaitProxyShutdown(opts, errCh, shutdownErrCh)
}

// awaitProxyShutdown waits for both ListenAndServe exit and coordinator drain.
// server.Shutdown unblocks ListenAndServe before later hooks (e.g. ClickHouse flush)
// finish; returning on errCh alone would drop buffered traces.
func awaitProxyShutdown(opts shutdownOpts, errCh, shutdownErrCh <-chan error) int {
	select {
	case err := <-errCh:
		if err != nil {
			opts.logger.ErrorCtx(context.Background(), "server failed", "error", err)
			triggerShutdownSignal(opts)
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
			opts.logger.ErrorCtx(context.Background(), "server failed", "error", err)
			return 1
		}
	}
	opts.logger.InfoCtx(context.Background(), "service stopped")
	return 0
}

// triggerShutdownSignal nudges an injected test signal channel so Wait can drain.
// Production coordinators listen on OS signals; process exit still reaps resources.
func triggerShutdownSignal(opts shutdownOpts) {
	if opts.signalCh == nil {
		return
	}
	select {
	case opts.signalCh <- syscall.SIGTERM:
	default:
	}
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
	// Drain in-flight HTTP before telemetry/providers tear down.
	sd.Register(func(ctx context.Context) error {
		return opts.server.Shutdown(ctx)
	})
	sd.Register(opts.providers.Shutdown)
	sd.Register(func(ctx context.Context) error {
		stopPubSubSubscribers(opts)
		return nil
	})
	registerOptionalShutdownHooks(sd, opts)
}

func registerOptionalShutdownHooks(sd *shutdown.Coordinator, opts shutdownOpts) {
	registerCheckpointPoolShutdown(sd, opts)
	registerSessionSweeperShutdown(sd, opts)
	registerTraceWriterShutdown(sd, opts)
	registerGRPCConnShutdown(sd, opts)
	registerRedisClientShutdown(sd, opts)
	registerPgDBShutdown(sd, opts)
}

func registerCheckpointPoolShutdown(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(ctx context.Context) error {
		if opts.checkpointPool == nil {
			return nil
		}
		return opts.checkpointPool.Shutdown(ctx)
	})
}

func registerSessionSweeperShutdown(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(ctx context.Context) error {
		if opts.sessionSweeper == nil {
			return nil
		}
		return opts.sessionSweeper.Stop(ctx)
	})
}

func registerTraceWriterShutdown(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(ctx context.Context) error {
		if opts.traceWriter == nil {
			return nil
		}
		return opts.traceWriter.Shutdown(ctx)
	})
}

func registerGRPCConnShutdown(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(ctx context.Context) error {
		if opts.grpcConn == nil {
			return nil
		}
		return opts.grpcConn.Close()
	})
}

func registerRedisClientShutdown(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(ctx context.Context) error {
		if opts.redisClient == nil {
			return nil
		}
		return opts.redisClient.Close()
	})
}

func registerPgDBShutdown(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(func(ctx context.Context) error {
		if opts.pgDB == nil {
			return nil
		}
		return opts.pgDB.Close()
	})
}
