// Package shutdown provides a reusable graceful shutdown coordinator.
// Both auth and proxy services import this package.
package shutdown

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
)

// Handler runs during shutdown with a drain deadline context.
type Handler func(ctx context.Context) error

// Coordinator manages ordered shutdown of registered components.
type Coordinator struct {
	timeout  time.Duration
	log      *slog.Logger
	signals  chan os.Signal
	handlers []Handler
}

// New creates a Coordinator that listens for SIGTERM and SIGINT.
func New(timeout time.Duration, log *slog.Logger) *Coordinator {
	return &Coordinator{timeout: timeout, log: log}
}

// NewWithSignalChan creates a Coordinator for tests with an injected signal channel.
func NewWithSignalChan(timeout time.Duration, log *slog.Logger, signals chan os.Signal) *Coordinator {
	return &Coordinator{timeout: timeout, log: log, signals: signals}
}

// Register adds a shutdown handler. Handlers run in registration order.
func (c *Coordinator) Register(fn Handler) {
	c.handlers = append(c.handlers, fn)
}

// Wait blocks until a signal is received, then runs handlers within the drain timeout.
func (c *Coordinator) Wait() error {
	sig := c.waitForSignal()
	c.log.Info("shutdown signal received", "signal", sig.String())

	immediate := sig == syscall.SIGINT
	drain := c.drainTimeout(sig)
	ctx, cancel := context.WithTimeout(context.Background(), drain)
	defer cancel()

	for _, fn := range c.handlers {
		if err := fn(ctx); err != nil {
			c.log.Error("shutdown handler error", "error", err)
		}
	}

	if immediate {
		c.log.Info("shutdown complete")
		return nil
	}
	if ctx.Err() != nil {
		c.log.Error("shutdown drain timeout exceeded; some requests may have been dropped")
		return ctx.Err()
	}
	c.log.Info("shutdown complete")
	return nil
}

func (c *Coordinator) waitForSignal() os.Signal {
	if c.signals != nil {
		return <-c.signals
	}
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(quit)
	return <-quit
}

func (c *Coordinator) drainTimeout(sig os.Signal) time.Duration {
	if sig == syscall.SIGINT {
		return 0
	}
	return c.timeout
}

// GracefulStopGRPC stops the gRPC server gracefully or forces Stop on ctx expiry.
func GracefulStopGRPC(srv *grpc.Server, ctx context.Context) error {
	if srv == nil {
		return nil
	}
	done := make(chan struct{})
	go func() {
		srv.GracefulStop()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		srv.Stop()
		return ctx.Err()
	}
}
