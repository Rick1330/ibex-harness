package redissub

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// OrgInvalidator drops cached state for an organization.
type OrgInvalidator interface {
	Invalidate(orgID uuid.UUID)
}

// OrgSubscriberConfig wires a domain-specific invalidate subscriber.
type OrgSubscriberConfig struct {
	Client        redis.UniversalClient
	Cache         OrgInvalidator
	Log           *logger.Logger
	ChannelPrefix string
	ErrPrefix     string
	Parse         func(payload string) (orgID string, err error)
	MalformedLog  string
	ChannelBadLog string
	MismatchLog   string
}

// OrgSubscriber PSUBSCRIBEs and invalidates on validated events.
type OrgSubscriber struct {
	client        redis.UniversalClient
	cache         OrgInvalidator
	log           *logger.Logger
	channelPrefix string
	errPrefix     string
	parse         func(payload string) (orgID string, err error)
	malformedLog  string
	channelBadLog string
	mismatchLog   string
	loop          *Loop
}

// NewOrgSubscriber constructs an OrgSubscriber.
func NewOrgSubscriber(cfg OrgSubscriberConfig) (*OrgSubscriber, error) {
	prefix := orErr(cfg.ErrPrefix)
	if cfg.Client == nil {
		return nil, fmt.Errorf("%s: redis client is required", prefix)
	}
	if cfg.Cache == nil {
		return nil, fmt.Errorf("%s: cache is required", prefix)
	}
	if cfg.Log == nil {
		return nil, fmt.Errorf("%s: logger is required", prefix)
	}
	if cfg.Parse == nil {
		return nil, fmt.Errorf("%s: parse is required", prefix)
	}
	return &OrgSubscriber{
		client:        cfg.Client,
		cache:         cfg.Cache,
		log:           cfg.Log,
		channelPrefix: cfg.ChannelPrefix,
		errPrefix:     prefix,
		parse:         cfg.Parse,
		malformedLog:  defaultLog(cfg.MalformedLog, "malformed invalidate event"),
		channelBadLog: defaultLog(cfg.ChannelBadLog, "invalidate channel invalid"),
		mismatchLog:   defaultLog(cfg.MismatchLog, "invalidate event org mismatch"),
		loop:          NewLoop(),
	}, nil
}

// Run blocks until Stop or ctx cancellation.
func (s *OrgSubscriber) Run(ctx context.Context, name string) {
	s.loop.Run(ctx, s.log, name, s.listenOnce)
}

// Stop cancels the listen context and signals the loop.
func (s *OrgSubscriber) Stop() { s.loop.Stop() }

// Done is closed when Run returns.
func (s *OrgSubscriber) Done() <-chan struct{} { return s.loop.Done() }

func (s *OrgSubscriber) listenOnce(ctx context.Context) (bool, error) {
	pubsub := s.client.PSubscribe(ctx, ChannelPattern(s.channelPrefix))
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
				return true, fmt.Errorf("%s: pubsub channel closed", s.errPrefix)
			}
			s.handleMessage(ctx, msg.Channel, msg.Payload)
		}
	}
}

func (s *OrgSubscriber) handleMessage(ctx context.Context, channel, payload string) {
	orgStr, err := s.parse(payload)
	if err != nil {
		s.log.WarnCtx(ctx, s.malformedLog, "error", err)
		return
	}
	orgFromChannel, err := OrgIDFromChannel(s.channelPrefix, channel)
	if err != nil {
		s.log.WarnCtx(ctx, s.channelBadLog, "error", err)
		return
	}
	orgID, err := uuid.Parse(orgStr)
	if err != nil || orgID != orgFromChannel {
		s.log.WarnCtx(ctx, s.mismatchLog, "channel_org", orgFromChannel, "event_org", orgStr)
		return
	}
	s.cache.Invalidate(orgID)
}

func defaultLog(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}
