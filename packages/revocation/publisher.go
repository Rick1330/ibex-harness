package revocation

import (
	"context"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/redis/go-redis/v9"
)

// PublishTimeout bounds a single Redis PUBLISH attempt.
const PublishTimeout = 2 * time.Second

// Publisher publishes revocation events (may be a no-op).
type Publisher interface {
	Publish(ctx context.Context, event RevocationEvent) error
}

// PublishMetrics records publish outcomes (result is "ok" or "error").
type PublishMetrics interface {
	IncRevocationPublish(result string)
}

// NoopPublishMetrics discards publish metric updates.
type NoopPublishMetrics struct{}

// IncRevocationPublish implements PublishMetrics.
func (NoopPublishMetrics) IncRevocationPublish(string) {
	// Intentionally empty: no-op metrics sink when Prometheus is not wired.
}

// RedisPublisher PUBLISHes JSON events to Channel.
type RedisPublisher struct {
	client  redis.UniversalClient
	log     *logger.Logger
	metrics PublishMetrics
}

// NewRedisPublisher constructs a RedisPublisher. metrics may be nil.
func NewRedisPublisher(client redis.UniversalClient, log *logger.Logger, metrics PublishMetrics) (*RedisPublisher, error) {
	if client == nil {
		return nil, fmt.Errorf("revocation: redis client is required")
	}
	if log == nil {
		return nil, fmt.Errorf("revocation: logger is required")
	}
	if metrics == nil {
		metrics = NoopPublishMetrics{}
	}
	return &RedisPublisher{client: client, log: log, metrics: metrics}, nil
}

// Publish encodes and PUBLISHes the event. Callers should treat errors as non-fatal.
func (p *RedisPublisher) Publish(ctx context.Context, event RevocationEvent) error {
	payload, err := event.Marshal()
	if err != nil {
		p.metrics.IncRevocationPublish("error")
		return err
	}
	pubCtx, cancel := context.WithTimeout(ctx, PublishTimeout)
	defer cancel()
	if err := p.client.Publish(pubCtx, Channel, payload).Err(); err != nil {
		p.metrics.IncRevocationPublish("error")
		return fmt.Errorf("revocation: publish: %w", err)
	}
	p.metrics.IncRevocationPublish("ok")
	return nil
}

// NoopPublisher discards events (used when Redis is not configured).
type NoopPublisher struct{}

// Publish implements Publisher.
func (NoopPublisher) Publish(context.Context, RevocationEvent) error { return nil }
