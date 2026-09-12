package modelpolicy

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// Invalidator drops cached policies for an org.
type Invalidator interface {
	Invalidate(orgID uuid.UUID)
}

// Subscriber listens for model-policy invalidate events.
type Subscriber struct {
	client  redis.UniversalClient
	cache   Invalidator
	log     *logger.Logger
	metrics Metrics
	loop    *redissub.Loop
}

// NewSubscriber constructs a Subscriber.
func NewSubscriber(
	client redis.UniversalClient,
	cache Invalidator,
	log *logger.Logger,
	metrics Metrics,
) (*Subscriber, error) {
	if client == nil {
		return nil, fmt.Errorf("modelpolicy: redis client is required")
	}
	if cache == nil {
		return nil, fmt.Errorf("modelpolicy: cache is required")
	}
	if log == nil {
		return nil, fmt.Errorf("modelpolicy: logger is required")
	}
	if metrics == nil {
		metrics = NoopMetrics{}
	}
	return &Subscriber{
		client:  client,
		cache:   cache,
		log:     log,
		metrics: metrics,
		loop:    redissub.NewLoop(),
	}, nil
}

// Run blocks until Stop or ctx cancellation.
func (s *Subscriber) Run(ctx context.Context) {
	s.loop.Run(ctx, s.log, "modelpolicy", s.listenOnce)
}

// Stop signals the subscriber to exit.
func (s *Subscriber) Stop() { s.loop.Stop() }

// Done is closed when Run returns.
func (s *Subscriber) Done() <-chan struct{} { return s.loop.Done() }

func (s *Subscriber) listenOnce(ctx context.Context) (bool, error) {
	pubsub := s.client.PSubscribe(ctx, ChannelPattern)
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
				return true, fmt.Errorf("modelpolicy: pubsub channel closed")
			}
			s.handleMessage(ctx, msg.Channel, msg.Payload)
		}
	}
}

func (s *Subscriber) handleMessage(ctx context.Context, channel, payload string) {
	event, err := ParseInvalidateEvent(payload)
	if err != nil {
		s.log.WarnCtx(ctx, "malformed model policy update event", "error", err)
		return
	}
	orgFromChannel, err := OrgIDFromChannel(channel)
	if err != nil {
		s.log.WarnCtx(ctx, "model policy channel invalid", "error", err)
		return
	}
	orgID, err := uuid.Parse(event.OrgID)
	if err != nil || orgID != orgFromChannel {
		s.log.WarnCtx(ctx, "model policy event org mismatch", "channel_org", orgFromChannel, "event_org", event.OrgID)
		return
	}
	s.cache.Invalidate(orgID)
}
