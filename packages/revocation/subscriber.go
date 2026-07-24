package revocation

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
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
// Intentionally empty: used when Prometheus is not wired (unit tests, Noop sinks).
func (NoopIncRevocationInvalidater) IncRevocationInvalidate() {
	// No-op: metrics sink unused when Prometheus is not wired.
}

// Subscriber listens on Channel and invalidates the local auth cache.
type Subscriber struct {
	client  redis.UniversalClient
	cache   Invalidator
	log     *logger.Logger
	metrics IncRevocationInvalidater
	loop    *redissub.Loop
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
		loop:    redissub.NewLoop(),
	}, nil
}

// Run blocks until Stop or ctx cancellation. Reconnects with backoff on errors.
func (s *Subscriber) Run(ctx context.Context) {
	s.loop.Run(ctx, s.log, "revocation", s.listenOnce)
}

// Stop signals the subscriber to exit. Safe if Run was never started.
func (s *Subscriber) Stop() { s.loop.Stop() }

// Done is closed when Run returns.
func (s *Subscriber) Done() <-chan struct{} { return s.loop.Done() }

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
		case <-s.loop.StopCh():
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
