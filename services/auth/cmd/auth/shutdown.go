package main

import (
	"context"
	"database/sql"
	"errors"
	"net"
	"net/http"
	"os"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/shutdown"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/auth/internal/config"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
)

type shutdownOpts struct {
	cfg         config.Config
	logger      *logger.Logger
	providers   *telemetry.Providers
	grpcSrv     *grpc.Server
	grpcLis     net.Listener
	httpServer  *http.Server
	httpLis     net.Listener // optional; when set, Serve(lis) instead of ListenAndServe
	db          *sql.DB
	redisClient redis.UniversalClient
	tokenSvc    *service.TokenService
	signalCh    chan os.Signal
}

func runWithShutdown(opts shutdownOpts) int {
	errCh := make(chan error, 2)
	startAuthGRPCServer(opts, errCh)
	startAuthHTTPServer(opts, errCh)

	sd := newAuthShutdownCoordinator(opts)
	registerAuthShutdownHooks(sd, opts)

	shutdownErrCh := make(chan error, 1)
	go func() { shutdownErrCh <- sd.Wait() }()

	return awaitAuthShutdown(errCh, shutdownErrCh, opts.logger)
}

func startAuthGRPCServer(opts shutdownOpts, errCh chan<- error) {
	go func() {
		opts.logger.InfoCtx(context.Background(), "grpc starting", "port", opts.cfg.GRPCPort)
		if err := opts.grpcSrv.Serve(opts.grpcLis); err != nil {
			errCh <- err
			return
		}
		errCh <- nil
	}()
}

func startAuthHTTPServer(opts shutdownOpts, errCh chan<- error) {
	go func() {
		opts.logger.InfoCtx(context.Background(), "http starting", "port", opts.cfg.Port, "env", opts.cfg.Environment)
		var err error
		if opts.httpLis != nil {
			err = opts.httpServer.Serve(opts.httpLis)
		} else {
			err = opts.httpServer.ListenAndServe()
		}
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
		errCh <- nil
	}()
}

func newAuthShutdownCoordinator(opts shutdownOpts) *shutdown.Coordinator {
	if opts.signalCh != nil {
		return shutdown.NewWithSignalChan(opts.cfg.ShutdownTimeout, opts.logger, opts.signalCh)
	}
	return shutdown.New(opts.cfg.ShutdownTimeout, opts.logger)
}

func awaitAuthShutdown(errCh, shutdownErrCh <-chan error, log *logger.Logger) int {
	for {
		select {
		case err := <-errCh:
			if err != nil {
				log.ErrorCtx(context.Background(), "server failed", "error", err)
				return 1
			}
			// Server exited cleanly (typically after Shutdown); wait for coordinator.
		case err := <-shutdownErrCh:
			return exitCodeForShutdownComplete(err, log)
		}
	}
}

func exitCodeForShutdownComplete(err error, log *logger.Logger) int {
	if err != nil {
		return 1
	}
	log.InfoCtx(context.Background(), "service stopped")
	return 0
}

func registerAuthShutdownHooks(sd *shutdown.Coordinator, opts shutdownOpts) {
	sd.Register(opts.providers.Shutdown)
	sd.Register(func(ctx context.Context) error {
		return shutdown.GracefulStopGRPC(opts.grpcSrv, ctx)
	})
	sd.Register(func(ctx context.Context) error {
		return opts.httpServer.Shutdown(ctx)
	})
	sd.Register(func(ctx context.Context) error {
		if opts.tokenSvc != nil {
			opts.tokenSvc.DrainPublishes()
		}
		return nil
	})
	sd.Register(func(ctx context.Context) error {
		return opts.db.Close()
	})
	sd.Register(func(ctx context.Context) error {
		if opts.redisClient != nil {
			return opts.redisClient.Close()
		}
		return nil
	})
}
