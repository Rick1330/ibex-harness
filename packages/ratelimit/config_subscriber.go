package ratelimit

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/redissub"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// DefaultConfigPollInterval is the full-override poll fallback period.
const DefaultConfigPollInterval = 30 * time.Second

// OverrideLoader loads rate_limit_overrides from Postgres (or a test fake).
type OverrideLoader interface {
	LoadOrg(ctx context.Context, orgID uuid.UUID) (OrgOverrideSet, error)
	LoadAll(ctx context.Context) (map[uuid.UUID]OrgOverrideSet, error)
}

// ConfigApplier applies DB override snapshots onto a live limiter.
type ConfigApplier interface {
	ApplyOrgOverrides(orgID uuid.UUID, set OrgOverrideSet)
	ReplaceAllOverrides(all map[uuid.UUID]OrgOverrideSet)
}

// ConfigSubscriberDeps bundles NewConfigSubscriber inputs (keeps arity low).
type ConfigSubscriberDeps struct {
	Client    redis.UniversalClient
	Store     OverrideLoader
	Applier   ConfigApplier
	Log       *logger.Logger
	PollEvery time.Duration
}

// ConfigSubscriber reloads overrides on pub/sub and periodic poll.
type ConfigSubscriber struct {
	client    redis.UniversalClient
	store     OverrideLoader
	applier   ConfigApplier
	log       *logger.Logger
	loop      *redissub.Loop
	pollEvery time.Duration
	// applyMu serializes each Load* → Apply*/Replace* sequence so poll and
	// pub/sub cannot interleave partial snapshots.
	applyMu sync.Mutex
}

// NewConfigSubscriber constructs a ConfigSubscriber. PollEvery defaults to 30s when <= 0.
func NewConfigSubscriber(deps ConfigSubscriberDeps) (*ConfigSubscriber, error) {
	if deps.Client == nil {
		return nil, fmt.Errorf("ratelimit: redis client is required")
	}
	if deps.Store == nil {
		return nil, fmt.Errorf("ratelimit: config store is required")
	}
	if deps.Applier == nil {
		return nil, fmt.Errorf("ratelimit: config applier is required")
	}
	if deps.Log == nil {
		return nil, fmt.Errorf("ratelimit: logger is required")
	}
	pollEvery := deps.PollEvery
	if pollEvery <= 0 {
		pollEvery = DefaultConfigPollInterval
	}
	return &ConfigSubscriber{
		client:    deps.Client,
		store:     deps.Store,
		applier:   deps.Applier,
		log:       deps.Log,
		loop:      redissub.NewLoop(),
		pollEvery: pollEvery,
	}, nil
}

// Ensure ConfigStore implements OverrideLoader.
var _ OverrideLoader = (*ConfigStore)(nil)

// Run blocks until Stop or ctx cancellation. Reconnects pub/sub with backoff
// and runs an independent 30s full poll in a sibling goroutine.
func (s *ConfigSubscriber) Run(ctx context.Context) {
	pollCtx, pollCancel := context.WithCancel(ctx)
	defer pollCancel()
	go s.pollLoop(pollCtx)
	s.loop.Run(ctx, s.log, "ratelimit-config", s.listenOnce)
}

// Stop signals the subscriber to exit.
func (s *ConfigSubscriber) Stop() { s.loop.Stop() }

// Done is closed when Run returns.
func (s *ConfigSubscriber) Done() <-chan struct{} { return s.loop.Done() }

func (s *ConfigSubscriber) listenOnce(ctx context.Context) (bool, error) {
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
				return true, fmt.Errorf("ratelimit: config pubsub channel closed")
			}
			s.handleMessage(ctx, msg.Channel, msg.Payload)
		}
	}
}

func (s *ConfigSubscriber) handleMessage(ctx context.Context, channel, payload string) {
	event, err := ParseConfigUpdateEvent(payload)
	if err != nil {
		s.log.WarnCtx(ctx, "malformed rate-limit config event", "error", err)
		return
	}
	orgID, ok := s.resolveEventOrg(ctx, channel, event)
	if !ok {
		return
	}
	s.applyMu.Lock()
	defer s.applyMu.Unlock()
	set, err := s.store.LoadOrg(ctx, orgID)
	if err != nil {
		s.log.WarnCtx(ctx, "rate-limit config reload failed; keeping prior overrides",
			"org_id", orgID.String(), "error", err)
		return
	}
	s.applier.ApplyOrgOverrides(orgID, set)
}

func (s *ConfigSubscriber) resolveEventOrg(
	ctx context.Context, channel string, event ConfigUpdateEvent,
) (uuid.UUID, bool) {
	orgFromChannel, err := OrgIDFromChannel(channel)
	if err != nil {
		s.log.WarnCtx(ctx, "rate-limit config channel invalid", "error", err)
		return uuid.Nil, false
	}
	orgID, err := uuid.Parse(event.OrgID)
	if err != nil || orgID != orgFromChannel {
		s.log.WarnCtx(ctx, "rate-limit config event org mismatch",
			"channel_org", orgFromChannel.String(), "payload_org", event.OrgID)
		return uuid.Nil, false
	}
	return orgID, true
}

func (s *ConfigSubscriber) pollLoop(ctx context.Context) {
	s.pollOnce(ctx)
	ticker := time.NewTicker(s.pollEvery)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-s.loop.StopCh():
			return
		case <-ticker.C:
			s.pollOnce(ctx)
		}
	}
}

func (s *ConfigSubscriber) pollOnce(ctx context.Context) {
	s.applyMu.Lock()
	defer s.applyMu.Unlock()
	all, err := s.store.LoadAll(ctx)
	if err != nil {
		s.log.WarnCtx(ctx, "rate-limit config poll failed; keeping prior overrides", "error", err)
		return
	}
	s.applier.ReplaceAllOverrides(all)
}

// Ensure HierarchicalLimiter implements ConfigApplier.
var _ ConfigApplier = (*HierarchicalLimiter)(nil)
