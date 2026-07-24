// Package redissub provides a reconnecting Redis pub/sub run loop shared by
// proxy cache invalidation subscribers (revocation, directive updates).
package redissub

import (
	"context"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
)

const (
	initialBackoff = time.Second
	maxBackoff     = 30 * time.Second
	stopWait       = 5 * time.Second
)

// ListenOnce establishes one subscription session. established is true once
// Subscribe/Receive succeeded (even if the session later ends).
type ListenOnce func(ctx context.Context) (established bool, err error)

// Loop owns stop/done channels and the reconnect-with-backoff Run cycle.
type Loop struct {
	stopOnce sync.Once
	stopCh   chan struct{}
	doneCh   chan struct{}
}

// NewLoop constructs a Loop ready for Run.
func NewLoop() *Loop {
	return &Loop{
		stopCh: make(chan struct{}),
		doneCh: make(chan struct{}),
	}
}

// StopCh is closed when Stop is called.
func (l *Loop) StopCh() <-chan struct{} { return l.stopCh }

// Done is closed when Run returns.
func (l *Loop) Done() <-chan struct{} { return l.doneCh }

// Stop signals Run to exit and waits briefly for Done.
func (l *Loop) Stop() {
	l.stopOnce.Do(func() { close(l.stopCh) })
	select {
	case <-l.doneCh:
	case <-time.After(stopWait):
	}
}

// Stopped reports whether stop or ctx cancellation has been signaled.
func (l *Loop) Stopped(ctx context.Context) bool {
	select {
	case <-l.stopCh:
		return true
	case <-ctx.Done():
		return true
	default:
		return false
	}
}

// Run blocks until Stop or ctx cancellation. Reconnects with exponential backoff.
// name is used only in reconnect warning logs (e.g. "directive", "revocation").
func (l *Loop) Run(ctx context.Context, log *logger.Logger, name string, listen ListenOnce) {
	defer close(l.doneCh)
	backoff := initialBackoff
	for {
		if l.Stopped(ctx) {
			return
		}
		established, err := listen(ctx)
		if l.Stopped(ctx) {
			return
		}
		if established {
			backoff = initialBackoff
		}
		if err != nil {
			log.WarnCtx(ctx, name+" subscriber disconnected; reconnecting",
				"error", err, "backoff", backoff.String())
		}
		if !l.sleepBackoff(ctx, backoff) {
			return
		}
		if backoff < maxBackoff {
			backoff *= 2
		}
	}
}

func (l *Loop) sleepBackoff(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-t.C:
		return true
	case <-l.stopCh:
		return false
	case <-ctx.Done():
		return false
	}
}
