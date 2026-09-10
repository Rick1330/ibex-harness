package ratelimit

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

// ConfigPublishTimeout bounds a single Redis PUBLISH attempt.
const ConfigPublishTimeout = 2 * time.Second

// ConfigPublisher PUBLISHes invalidate events to ratelimit_config_updates:{org_id}.
type ConfigPublisher struct {
	client redis.UniversalClient
	log    *logger.Logger
	tracer trace.Tracer
}

// NewConfigPublisher constructs a ConfigPublisher.
func NewConfigPublisher(client redis.UniversalClient, log *logger.Logger) (*ConfigPublisher, error) {
	if client == nil {
		return nil, fmt.Errorf("ratelimit: redis client is required")
	}
	if log == nil {
		return nil, fmt.Errorf("ratelimit: logger is required")
	}
	return &ConfigPublisher{
		client: client,
		log:    log,
		tracer: otel.Tracer("ibex-ratelimit"),
	}, nil
}

// Publish encodes and PUBLISHes the event to the org channel.
func (p *ConfigPublisher) Publish(ctx context.Context, event ConfigUpdateEvent) error {
	payload, err := event.Marshal()
	if err != nil {
		return err
	}
	orgID, err := uuid.Parse(event.OrgID)
	if err != nil {
		return fmt.Errorf("ratelimit: org_id: %w", err)
	}
	pubCtx, cancel := context.WithTimeout(ctx, ConfigPublishTimeout)
	defer cancel()
	channel := ChannelForOrg(orgID)
	pubCtx, span := p.tracer.Start(pubCtx, "ratelimit.ConfigPublish")
	defer span.End()
	if err := p.client.Publish(pubCtx, channel, payload).Err(); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("ratelimit: publish: %w", err)
	}
	return nil
}

// NoopConfigPublisher discards events when Redis is not configured.
type NoopConfigPublisher struct{}

// Publish discards the event.
func (NoopConfigPublisher) Publish(context.Context, ConfigUpdateEvent) error {
	return nil
}
