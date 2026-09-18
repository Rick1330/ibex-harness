package billing

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	lru "github.com/hashicorp/golang-lru/v2"
)

const maxBudgetLoadAttempts = 3

type cachedBudget struct {
	snap      BudgetSnapshot
	expiresAt time.Time
	gen       uint64
}

// Cache is a process-local LRU + TTL budget cache in front of BudgetLoader.
// Invalidate advances a per-org generation so in-flight loads cannot repopulate
// a stale snapshot (fail-closed spend caps).
type Cache struct {
	loader  BudgetLoader
	cfg     Config
	metrics Metrics
	lru     *lru.Cache[string, *cachedBudget]
	now     func() time.Time

	mu   sync.Mutex
	gens map[string]uint64
}

// NewCache constructs a Cache. loader is required.
func NewCache(loader BudgetLoader, cfg Config, m Metrics) (*Cache, error) {
	if loader == nil {
		return nil, fmt.Errorf("billing: loader is required")
	}
	if m == nil {
		m = NoopMetrics{}
	}
	cfg.ApplyDefaults()
	c := &Cache{
		loader:  loader,
		cfg:     cfg,
		metrics: m,
		now:     time.Now,
		gens:    make(map[string]uint64),
	}
	cache, err := lru.NewWithEvict[string, *cachedBudget](cfg.LRUSize, c.onLRUEvict)
	if err != nil {
		return nil, fmt.Errorf("billing: lru: %w", err)
	}
	c.lru = cache
	return c, nil
}

func (c *Cache) onLRUEvict(key string, entry *cachedBudget) {
	// Keep c.gens[key] so generations stay monotonic. Deleting on eviction would
	// let a stale in-flight load pass installSnapshot via the map's zero value.
	_ = key
	_ = entry
}

// Check returns whether the org may proceed under its hard_cap (if any).
// Loader/cache failures return ErrBudgetUnavailable (fail closed).
func (c *Cache) Check(ctx context.Context, orgID uuid.UUID) (allowed bool, remainingCents int64, err error) {
	if orgID == uuid.Nil {
		return false, 0, fmt.Errorf("%w: nil org_id", ErrBudgetUnavailable)
	}
	snap, err := c.SnapshotForOrg(ctx, orgID)
	if err != nil {
		return false, 0, err
	}
	if !snap.HasHardCap {
		return true, snap.RemainingCents(), nil
	}
	rem := snap.RemainingCents()
	if rem <= 0 || snap.SpentCents >= snap.CapCents {
		c.metrics.IncDeny()
		return false, 0, nil
	}
	return true, rem, nil
}

// SnapshotForOrg returns cached or freshly loaded budget state.
func (c *Cache) SnapshotForOrg(ctx context.Context, orgID uuid.UUID) (BudgetSnapshot, error) {
	key := orgID.String()
	if snap, ok := c.lookupFresh(key); ok {
		c.metrics.IncCacheHit("lru")
		return snap, nil
	}
	c.metrics.IncCacheMiss("lru")
	return c.loadAndStore(ctx, orgID, key)
}

// PublishedCard returns the cached published rate card for write-time freeze.
func (c *Cache) PublishedCard(ctx context.Context, orgID uuid.UUID) (CardVersion, error) {
	snap, err := c.SnapshotForOrg(ctx, orgID)
	if err != nil {
		return CardVersion{}, err
	}
	return snap.PublishedCard, nil
}

func (c *Cache) lookupFresh(key string) (BudgetSnapshot, bool) {
	c.mu.Lock()
	entry, ok := c.lru.Get(key)
	if !ok || entry == nil {
		c.mu.Unlock()
		return BudgetSnapshot{}, false
	}
	if entry.gen != c.gens[key] {
		c.mu.Unlock()
		c.lru.Remove(key)
		return BudgetSnapshot{}, false
	}
	if !c.now().Before(entry.expiresAt) {
		c.mu.Unlock()
		c.lru.Remove(key)
		return BudgetSnapshot{}, false
	}
	out := entry.snap
	c.mu.Unlock()
	return out, true
}

func (c *Cache) loadAndStore(ctx context.Context, orgID uuid.UUID, key string) (BudgetSnapshot, error) {
	loadCtx := ctx
	if c.cfg.LoadTimeout > 0 {
		var cancel context.CancelFunc
		loadCtx, cancel = context.WithTimeout(ctx, c.cfg.LoadTimeout)
		defer cancel()
	}
	for attempt := 0; attempt < maxBudgetLoadAttempts; attempt++ {
		snap, ok, err := c.loadOnce(loadCtx, orgID, key)
		if err != nil {
			return BudgetSnapshot{}, err
		}
		if ok {
			return snap, nil
		}
	}
	return BudgetSnapshot{}, fmt.Errorf("%w: invalidated during load", ErrBudgetUnavailable)
}

func (c *Cache) loadOnce(ctx context.Context, orgID uuid.UUID, key string) (BudgetSnapshot, bool, error) {
	c.mu.Lock()
	gen := c.gens[key]
	c.mu.Unlock()

	snap, err := c.loader.LoadOrg(ctx, orgID)
	if err != nil {
		return BudgetSnapshot{}, false, fmt.Errorf("%w: %w", ErrBudgetUnavailable, err)
	}
	return c.installSnapshot(key, gen, snap)
}

func (c *Cache) installSnapshot(key string, gen uint64, snap BudgetSnapshot) (BudgetSnapshot, bool, error) {
	c.mu.Lock()
	if c.gens[key] != gen {
		c.mu.Unlock()
		return BudgetSnapshot{}, false, nil
	}
	entry := &cachedBudget{
		snap:      snap,
		expiresAt: c.now().Add(c.cfg.CacheTTL),
		gen:       gen,
	}
	c.mu.Unlock()

	c.lru.Add(key, entry)

	c.mu.Lock()
	stale := c.gens[key] != gen
	size := c.lru.Len()
	c.mu.Unlock()
	if stale {
		c.removeIfSame(key, entry)
		return BudgetSnapshot{}, false, nil
	}
	c.metrics.SetLRUSize(float64(size))
	return snap, true, nil
}

func (c *Cache) removeIfSame(key string, want *cachedBudget) {
	if want == nil {
		return
	}
	if got, ok := c.lru.Peek(key); ok && got == want {
		c.lru.Remove(key)
	}
}

// Invalidate drops the LRU entry for orgID and advances its generation.
func (c *Cache) Invalidate(orgID uuid.UUID) {
	if orgID == uuid.Nil {
		return
	}
	key := orgID.String()
	c.mu.Lock()
	c.gens[key]++
	c.mu.Unlock()
	c.lru.Remove(key)
	c.mu.Lock()
	size := c.lru.Len()
	c.mu.Unlock()
	c.metrics.IncInvalidate()
	c.metrics.SetLRUSize(float64(size))
}
