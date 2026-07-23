package revocation

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/redis/go-redis/v9"
)

// Invalidator removes a cached claims entry by token UUID.
type Invalidator interface {
	InvalidateByTokenID(tokenID string)
}

// IncRevocationInvalidater records successful invalidate deliveries.
type IncRevocationInvalidater interface {
	IncRevocationInvalidate()
}

// NoopIncRevocationInvalidater discards invalidate metric updates.
type NoopIncRevocationInvalidater struct{}

// IncRevocationInvalidate implements IncRevocationInvalidater.
func (NoopIncRevocationInvalidater) IncRevocationInvalidate() {
	// Intentionally empty: no-op metrics sink when Prometheus is not wired.
}

// Subscriber listens on Channel and invalidates the local auth cache.
type Subscriber struct {
	client  redis.UniversalClient
	cache   Invalidator
	log     *logger.Logger
	metrics IncRevocationInvalidater

	stopOnce sync.Once
	stopCh   chan struct{}
	doneCh   chan struct{}
}

// NewSubscriber constructs a Subscriber. metrics may be nil.
func NewSubscriber(
	client redis.UniversalClient,
	cache Invalidator,
	log *logger.Logger,
	metrics IncRevocationInvalidater,
) (*Subscriber, error) {
	if client == nil {
		return nil, fmt.Errorf("revocation: redis client is required")
	}
	if cache == nil {
		return nil, fmt.Errorf("revocation: invalidator is required")
	}
	if log == nil {
		return nil, fmt.Errorf("revocation: logger is required")
	}
	if metrics == nil {
		metrics = NoopIncRevocationInvalidater{}
	}
	return &Subscriber{
		client:  client,
		cache:   cache,
		log:     log,
		metrics: metrics,
		stopCh:  make(chan struct{}),
		doneCh:  make(chan struct{}),
	}, nil
}

const (
	initialBackoff = time.Second
	maxBackoff     = 30 * time.Second
)

// Run blocks until Stop or ctx cancellation. Reconnects with backoff on errors.
// Backoff resets to 1s after any session that successfully subscribed.
func (s *Subscriber) Run(ctx context.Context) {
	defer close(s.doneCh)
	backoff := initialBackoff
	for {
		if s.stoppedOrDone(ctx) {
			return
		}
		established, err := s.listenOnce(ctx)
		if s.stoppedOrDone(ctx) {
			return
		}
		if established {
			backoff = initialBackoff
		}
		if err != nil {
			s.log.WarnCtx(ctx, "revocation subscriber disconnected; reconnecting",
				"error", err, "backoff", backoff.String())
		}
		if !s.sleepBackoff(ctx, backoff) {
			return
		}
		if backoff < maxBackoff {
			backoff *= 2
		}
	}
}

// Stop signals the subscriber to exit. Safe if Run was never started.
func (s *Subscriber) Stop() {
	s.stopOnce.Do(func() { close(s.stopCh) })
	select {
	case <-s.doneCh:
	case <-time.After(5 * time.Second):
	}
}

// Done is closed when Run returns.
func (s *Subscriber) Done() <-chan struct{} {
	return s.doneCh
}

func (s *Subscriber) stoppedOrDone(ctx context.Context) bool {
	select {
	case <-s.stopCh:
		return true
	case <-ctx.Done():
		return true
	default:
		return false
	}
}

func (s *Subscriber) sleepBackoff(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-t.C:
		return true
	case <-s.stopCh:
		return false
	case <-ctx.Done():
		return false
	}
}

// listenOnce returns established=true once Subscribe/Receive succeeded.
func (s *Subscriber) listenOnce(ctx context.Context) (bool, error) {
	pubsub := s.client.Subscribe(ctx, Channel)
	defer func() { _ = pubsub.Close() }()

	if _, err := pubsub.Receive(ctx); err != nil {
		return false, err
	}
	ch := pubsub.Channel()
	for {
		select {
		case <-s.stopCh:
			return true, nil
		case <-ctx.Done():
			return true, nil
		case msg, ok := <-ch:
			if !ok {
				return true, fmt.Errorf("revocation: pubsub channel closed")
			}
			s.handleMessage(ctx, msg.Payload)
		}
	}
}

func (s *Subscriber) handleMessage(ctx context.Context, payload string) {
	event, err := ParseEvent(payload)
	if err != nil {
		s.log.WarnCtx(ctx, "malformed revocation event", "error", err)
		return
	}
	s.cache.InvalidateByTokenID(event.TokenID)
	s.metrics.IncRevocationInvalidate()
}
