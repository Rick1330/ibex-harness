package modelpolicy

import (
	"context"

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
	inner   *redissub.OrgSubscriber
	metrics Metrics
}

// NewSubscriber constructs a Subscriber.
func NewSubscriber(
	client redis.UniversalClient,
	cache Invalidator,
	log *logger.Logger,
	metrics Metrics,
) (*Subscriber, error) {
	if metrics == nil {
		metrics = NoopMetrics{}
	}
	inner, err := redissub.NewOrgSubscriber(redissub.OrgSubscriberConfig{
		Client: client, Cache: cache, Log: log,
		ChannelPrefix: ChannelPrefix, ErrPrefix: "modelpolicy",
		Parse: func(payload string) (string, error) {
			ev, err := ParseInvalidateEvent(payload)
			if err != nil {
				return "", err
			}
			return ev.OrgID, nil
		},
		MalformedLog:  "malformed model policy update event",
		ChannelBadLog: "model policy channel invalid",
		MismatchLog:   "model policy event org mismatch",
	})
	if err != nil {
		return nil, err
	}
	return &Subscriber{inner: inner, metrics: metrics}, nil
}

// Run blocks until Stop or ctx cancellation.
func (s *Subscriber) Run(ctx context.Context) {
	s.inner.Run(ctx, "modelpolicy")
}

// Stop cancels the listen context (via redissub.Loop) and signals the loop.
func (s *Subscriber) Stop() { s.inner.Stop() }

// Done is closed when Run returns.
func (s *Subscriber) Done() <-chan struct{} { return s.inner.Done() }
