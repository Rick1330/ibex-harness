package modelpolicy

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// PublishTimeout bounds a single Redis PUBLISH attempt.
const PublishTimeout = redissub.PublishTimeout

// Publisher PUBLISHes invalidate events to model_policy_updates:{org_id}.
type Publisher interface {
	Publish(ctx context.Context, event InvalidateEvent) error
}

// RedisPublisher PUBLISHes JSON events.
type RedisPublisher struct {
	inner *redissub.OrgPublisher
}

// NewRedisPublisher constructs a RedisPublisher.
func NewRedisPublisher(client redis.UniversalClient, log *logger.Logger) (*RedisPublisher, error) {
	inner, err := redissub.NewOrgPublisher(redissub.OrgPublisherConfig{
		Client: client, Log: log, ChannelPrefix: ChannelPrefix, ErrPrefix: "modelpolicy",
		TracerName: "ibex-modelpolicy", SpanName: "modelpolicy.RedisPublish",
	})
	if err != nil {
		return nil, err
	}
	return &RedisPublisher{inner: inner}, nil
}

// Publish encodes and PUBLISHes the event to the org channel.
func (p *RedisPublisher) Publish(ctx context.Context, event InvalidateEvent) error {
	payload, err := event.Marshal()
	if err != nil {
		return err
	}
	orgID, err := uuid.Parse(event.OrgID)
	if err != nil {
		return fmt.Errorf("modelpolicy: org_id: %w", err)
	}
	return p.inner.PublishJSON(ctx, orgID, payload)
}

// NoopPublisher discards events when Redis is not configured.
type NoopPublisher struct{}

// Publish discards the event.
func (NoopPublisher) Publish(context.Context, InvalidateEvent) error { return nil }
