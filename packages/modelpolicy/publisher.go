package modelpolicy

import (
	"context"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// PublishTimeout bounds a single Redis PUBLISH attempt.
const PublishTimeout = 2 * time.Second

// Publisher PUBLISHes invalidate events to model_policy_updates:{org_id}.
type Publisher interface {
	Publish(ctx context.Context, event InvalidateEvent) error
}

// RedisPublisher PUBLISHes JSON events.
type RedisPublisher struct {
	client redis.UniversalClient
	log    *logger.Logger
	tracer trace.Tracer
}

// NewRedisPublisher constructs a RedisPublisher.
func NewRedisPublisher(client redis.UniversalClient, log *logger.Logger) (*RedisPublisher, error) {
	if client == nil {
		return nil, fmt.Errorf("modelpolicy: redis client is required")
	}
	if log == nil {
		return nil, fmt.Errorf("modelpolicy: logger is required")
	}
	return &RedisPublisher{
		client: client,
		log:    log,
		tracer: otel.Tracer("ibex-modelpolicy"),
	}, nil
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
	pubCtx, cancel := context.WithTimeout(ctx, PublishTimeout)
	defer cancel()
	channel := ChannelForOrg(orgID)
	pubCtx, span := p.tracer.Start(pubCtx, "modelpolicy.RedisPublish")
	defer span.End()
	if err := p.client.Publish(pubCtx, channel, payload).Err(); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("modelpolicy: publish: %w", err)
	}
	return nil
}

// NoopPublisher discards events when Redis is not configured.
type NoopPublisher struct{}

// Publish discards the event.
func (NoopPublisher) Publish(context.Context, InvalidateEvent) error { return nil }
