package redissub

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

// OrgPublisherConfig wires a domain-specific invalidate publisher.
type OrgPublisherConfig struct {
	Client        redis.UniversalClient
	Log           *logger.Logger
	ChannelPrefix string
	ErrPrefix     string
	TracerName    string
	SpanName      string
}

// OrgPublisher PUBLISHes opaque JSON payloads to org channels.
type OrgPublisher struct {
	client        redis.UniversalClient
	log           *logger.Logger
	channelPrefix string
	errPrefix     string
	tracer        trace.Tracer
	spanName      string
}

// NewOrgPublisher constructs an OrgPublisher.
func NewOrgPublisher(cfg OrgPublisherConfig) (*OrgPublisher, error) {
	if cfg.Client == nil {
		return nil, fmt.Errorf("%s: redis client is required", orErr(cfg.ErrPrefix))
	}
	if cfg.Log == nil {
		return nil, fmt.Errorf("%s: logger is required", orErr(cfg.ErrPrefix))
	}
	tracerName := cfg.TracerName
	if tracerName == "" {
		tracerName = "ibex-redissub"
	}
	span := cfg.SpanName
	if span == "" {
		span = "redissub.RedisPublish"
	}
	return &OrgPublisher{
		client:        cfg.Client,
		log:           cfg.Log,
		channelPrefix: cfg.ChannelPrefix,
		errPrefix:     orErr(cfg.ErrPrefix),
		tracer:        otel.Tracer(tracerName),
		spanName:      span,
	}, nil
}

// PublishJSON PUBLISHes payload to the org channel.
func (p *OrgPublisher) PublishJSON(ctx context.Context, orgID uuid.UUID, payload []byte) error {
	pubCtx, cancel := context.WithTimeout(ctx, PublishTimeout)
	defer cancel()
	channel := ChannelForOrg(p.channelPrefix, orgID)
	pubCtx, span := p.tracer.Start(pubCtx, p.spanName)
	defer span.End()
	if err := p.client.Publish(pubCtx, channel, payload).Err(); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return fmt.Errorf("%s: publish: %w", p.errPrefix, err)
	}
	return nil
}

func orErr(prefix string) string {
	if prefix == "" {
		return "redissub"
	}
	return prefix
}
