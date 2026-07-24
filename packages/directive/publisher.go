package directive

import (
	"context"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// PublishTimeout bounds a single Redis PUBLISH attempt.
const PublishTimeout = 2 * time.Second

// Publisher publishes directive update events (may be a no-op).
type Publisher interface {
	Publish(ctx context.Context, event UpdateEvent) error
}

// RedisPublisher PUBLISHes JSON events to directive_updates:{org_id}.
type RedisPublisher struct {
	client redis.UniversalClient
	log    *logger.Logger
}

// NewRedisPublisher constructs a RedisPublisher.
func NewRedisPublisher(client redis.UniversalClient, log *logger.Logger) (*RedisPublisher, error) {
	if client == nil {
		return nil, fmt.Errorf("directive: redis client is required")
	}
	if log == nil {
		return nil, fmt.Errorf("directive: logger is required")
	}
	return &RedisPublisher{client: client, log: log}, nil
}

// Publish encodes and PUBLISHes the event to the org channel.
func (p *RedisPublisher) Publish(ctx context.Context, event UpdateEvent) error {
	payload, err := event.Marshal()
	if err != nil {
		return err
	}
	orgID, err := uuid.Parse(event.OrgID)
	if err != nil {
		return fmt.Errorf("directive: org_id: %w", err)
	}
	pubCtx, cancel := context.WithTimeout(ctx, PublishTimeout)
	defer cancel()
	channel := ChannelForOrg(orgID)
	if err := p.client.Publish(pubCtx, channel, payload).Err(); err != nil {
		return fmt.Errorf("directive: publish: %w", err)
	}
	return nil
}

// NoopPublisher discards events.
type NoopPublisher struct{}

// Publish implements Publisher.
func (NoopPublisher) Publish(context.Context, UpdateEvent) error { return nil }
