package modelpolicy

import (
	"context"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/google/uuid"
)

// DefaultEpochPollInterval is the backstop poll cadence when pub/sub is lossy or absent.
const DefaultEpochPollInterval = 5 * time.Second

// EpochPoller periodically reloads durable epochs for cached orgs and invalidates on drift.
type EpochPoller struct {
	loader   PolicyLoader
	cache    *Cache
	log      *logger.Logger
	interval time.Duration
	now      func() time.Time
}

// NewEpochPoller constructs a poller. interval <=0 uses DefaultEpochPollInterval.
func NewEpochPoller(loader PolicyLoader, cache *Cache, log *logger.Logger, interval time.Duration) *EpochPoller {
	if interval <= 0 {
		interval = DefaultEpochPollInterval
	}
	return &EpochPoller{
		loader:   loader,
		cache:    cache,
		log:      log,
		interval: interval,
		now:      time.Now,
	}
}

// Run polls until ctx is cancelled.
func (p *EpochPoller) Run(ctx context.Context) {
	if p == nil || p.loader == nil || p.cache == nil {
		return
	}
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			p.pollOnce(ctx)
		}
	}
}

func (p *EpochPoller) pollOnce(ctx context.Context) {
	for _, orgID := range p.cache.cachedOrgIDs() {
		p.reconcileOrgEpoch(ctx, orgID)
	}
}

func (p *EpochPoller) reconcileOrgEpoch(ctx context.Context, orgID uuid.UUID) {
	cachedEpoch, ok := p.cache.CachedEpoch(orgID)
	if !ok {
		return
	}
	snap, err := p.loadOrgForPoll(ctx, orgID)
	if err != nil {
		if p.log != nil {
			p.log.WarnCtx(ctx, "model policy epoch poll failed", "org_id", orgID.String(), "err", err.Error())
		}
		// Fail closed for this org: drop cache so next request reloads or errors.
		// Timeouts use the same path so subsequent orgs continue to poll.
		p.cache.Invalidate(orgID)
		return
	}
	if snap.Epoch != cachedEpoch {
		p.cache.Invalidate(orgID)
	}
}

func (p *EpochPoller) loadOrgForPoll(ctx context.Context, orgID uuid.UUID) (OrgPolicies, error) {
	if p.cache.cfg.LoadTimeout <= 0 {
		return p.loader.LoadOrg(ctx, orgID)
	}
	loadCtx, cancel := context.WithTimeout(ctx, p.cache.cfg.LoadTimeout)
	defer cancel()
	return p.loader.LoadOrg(loadCtx, orgID)
}

func (c *Cache) cachedOrgIDs() []uuid.UUID {
	// Enumerate live LRU entries (not gens): Invalidate bumps gens while removing
	// the entry, and gens may retain keys after eviction. Keys() is the durable set
	// of organizations that still hold a cached snapshot.
	keys := c.lru.Keys()
	out := make([]uuid.UUID, 0, len(keys))
	for _, key := range keys {
		id, err := uuid.Parse(key)
		if err != nil {
			continue
		}
		out = append(out, id)
	}
	return out
}
