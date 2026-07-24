package directive

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

const (
	initialBackoff = time.Second
	maxBackoff     = 30 * time.Second
)

// Subscriber listens for directive update events and invalidates the cache.
type Subscriber struct {
	client  redis.UniversalClient
	cache   Resolver
	log     *logger.Logger
	metrics Metrics

	stopOnce sync.Once
	stopCh   chan struct{}
	doneCh   chan struct{}
}

// NewSubscriber constructs a Subscriber. metrics may be nil.
func NewSubscriber(
	client redis.UniversalClient,
	cache Resolver,
	log *logger.Logger,
	metrics Metrics,
) (*Subscriber, error) {
	if client == nil {
		return nil, fmt.Errorf("directive: redis client is required")
	}
	if cache == nil {
		return nil, fmt.Errorf("directive: resolver is required")
	}
	if log == nil {
		return nil, fmt.Errorf("directive: logger is required")
	}
	if metrics == nil {
		metrics = NoopMetrics{}
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

// Run blocks until Stop or ctx cancellation. Reconnects with backoff on errors.
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
			s.log.WarnCtx(ctx, "directive subscriber disconnected; reconnecting",
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

func (s *Subscriber) listenOnce(ctx context.Context) (bool, error) {
	pubsub := s.client.PSubscribe(ctx, ChannelPattern)
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
				return true, fmt.Errorf("directive: pubsub channel closed")
			}
			s.handleMessage(ctx, msg.Channel, msg.Payload)
		}
	}
}

func (s *Subscriber) handleMessage(ctx context.Context, channel, payload string) {
	event, err := ParseUpdateEvent(payload)
	if err != nil {
		s.log.WarnCtx(ctx, "malformed directive update event", "error", err)
		return
	}
	orgID, agentID, err := parseEventIDs(channel, event)
	if err != nil {
		s.log.WarnCtx(ctx, "directive update event ids invalid", "error", err)
		return
	}
	s.cache.Invalidate(orgID, agentID)
	s.metrics.IncDirectiveInvalidate()
}

func parseEventIDs(channel string, event UpdateEvent) (uuid.UUID, uuid.UUID, error) {
	orgFromChannel, err := OrgIDFromChannel(channel)
	if err != nil {
		return uuid.Nil, uuid.Nil, err
	}
	orgID, err := uuid.Parse(event.OrgID)
	if err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("org_id: %w", err)
	}
	if orgID != orgFromChannel {
		return uuid.Nil, uuid.Nil, fmt.Errorf("org_id mismatch channel vs payload")
	}
	agentID, err := uuid.Parse(event.AgentID)
	if err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("agent_id: %w", err)
	}
	return orgID, agentID, nil
}
