package modelpolicy

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	lru "github.com/hashicorp/golang-lru/v2"
)

const maxPolicyLoadAttempts = 3

type cachedPolicies struct {
	policies  []Policy
	epoch     uint64
	expiresAt time.Time
	gen       uint64
}

// Cache is a process-local LRU + TTL policy cache in front of PolicyLoader.
// Invalidate advances a per-org generation under the same lock used for install,
// so in-flight loads cannot repopulate a stale snapshot (ADR-0075 fail-closed).
// Entries also store the durable Postgres policy epoch (4.P.1).
type Cache struct {
	loader  PolicyLoader
	cfg     Config
	metrics Metrics
	lru     *lru.Cache[string, *cachedPolicies]
	now     func() time.Time

	mu   sync.Mutex
	gens map[string]uint64
}

// NewCache constructs a Cache. loader is required.
func NewCache(loader PolicyLoader, cfg Config, m Metrics) (*Cache, error) {
	if loader == nil {
		return nil, fmt.Errorf("modelpolicy: loader is required")
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
	cache, err := lru.NewWithEvict[string, *cachedPolicies](cfg.LRUSize, c.onLRUEvict)
	if err != nil {
		return nil, fmt.Errorf("modelpolicy: lru: %w", err)
	}
	c.lru = cache
	return c, nil
}

// onLRUEvict drops gens entries for capacity/TTL removals of the live generation.
// Invalidate bumps gens before Remove, so entry.gen != gens[key] and the bump is kept.
// Callers must not hold c.mu across lru.Add/Remove (evict runs synchronously).
func (c *Cache) onLRUEvict(key string, entry *cachedPolicies) {
	if entry == nil {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.gens[key] == entry.gen {
		delete(c.gens, key)
	}
}

// Loader returns the underlying PolicyLoader (for epoch poll backstop).
func (c *Cache) Loader() PolicyLoader {
	return c.loader
}

// PoliciesForOrg returns cached or freshly loaded policies for orgID.
// Loader errors and invalid patterns fail closed.
func (c *Cache) PoliciesForOrg(ctx context.Context, orgID uuid.UUID) ([]Policy, error) {
	snap, err := c.SnapshotForOrg(ctx, orgID)
	if err != nil {
		return nil, err
	}
	return snap.Policies, nil
}

// SnapshotForOrg returns policies plus durable epoch.
func (c *Cache) SnapshotForOrg(ctx context.Context, orgID uuid.UUID) (OrgPolicies, error) {
	key := orgID.String()
	if snap, ok := c.lookupFresh(key); ok {
		c.metrics.IncCacheHit("lru")
		return snap, nil
	}
	c.metrics.IncCacheMiss("lru")
	return c.loadAndStore(ctx, orgID, key)
}

// CachedEpoch returns the cached durable epoch when present and fresh.
func (c *Cache) CachedEpoch(orgID uuid.UUID) (uint64, bool) {
	key := orgID.String()
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.lru.Get(key)
	if !ok || entry == nil {
		return 0, false
	}
	if entry.gen != c.gens[key] {
		return 0, false
	}
	if !c.now().Before(entry.expiresAt) {
		return 0, false
	}
	return entry.epoch, true
}

func (c *Cache) lookupFresh(key string) (OrgPolicies, bool) {
	c.mu.Lock()
	entry, ok := c.lru.Get(key)
	if !ok || entry == nil {
		c.mu.Unlock()
		return OrgPolicies{}, false
	}
	if entry.gen != c.gens[key] {
		c.mu.Unlock()
		c.lru.Remove(key)
		return OrgPolicies{}, false
	}
	if !c.now().Before(entry.expiresAt) {
		c.mu.Unlock()
		c.lru.Remove(key)
		return OrgPolicies{}, false
	}
	out := OrgPolicies{Epoch: entry.epoch, Policies: clonePolicies(entry.policies)}
	c.mu.Unlock()
	return out, true
}

func (c *Cache) loadAndStore(ctx context.Context, orgID uuid.UUID, key string) (OrgPolicies, error) {
	loadCtx := ctx
	if c.cfg.LoadTimeout > 0 {
		var cancel context.CancelFunc
		loadCtx, cancel = context.WithTimeout(ctx, c.cfg.LoadTimeout)
		defer cancel()
	}
	for attempt := 0; attempt < maxPolicyLoadAttempts; attempt++ {
		snap, ok, err := c.loadOnce(loadCtx, orgID, key)
		if err != nil {
			return OrgPolicies{}, err
		}
		if ok {
			return snap, nil
		}
	}
	return OrgPolicies{}, fmt.Errorf("%w: invalidated during load", ErrPolicyUnavailable)
}

func (c *Cache) loadOnce(ctx context.Context, orgID uuid.UUID, key string) (OrgPolicies, bool, error) {
	c.mu.Lock()
	gen := c.gens[key]
	c.mu.Unlock()

	snap, err := c.loader.LoadOrg(ctx, orgID)
	if err != nil {
		return OrgPolicies{}, false, fmt.Errorf("%w: %w", ErrPolicyUnavailable, err)
	}
	if snap.Epoch < 1 {
		return OrgPolicies{}, false, fmt.Errorf("%w: missing policy epoch", ErrPolicyUnavailable)
	}
	if snap.Policies == nil {
		snap.Policies = []Policy{}
	}
	policies, err := validateLoadedPolicies(snap.Policies)
	if err != nil {
		return OrgPolicies{}, false, fmt.Errorf("%w: %w", ErrPolicyUnavailable, err)
	}
	snap.Policies = policies

	c.mu.Lock()
	if c.gens[key] != gen {
		c.mu.Unlock()
		return OrgPolicies{}, false, nil
	}
	entry := &cachedPolicies{
		policies:  clonePolicies(snap.Policies),
		epoch:     snap.Epoch,
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
		return OrgPolicies{}, false, nil
	}
	c.metrics.SetLRUSize(float64(size))
	return OrgPolicies{Epoch: snap.Epoch, Policies: clonePolicies(snap.Policies)}, true, nil
}

// removeIfSame drops key only when the LRU still holds want (pointer identity),
// preserving a newer same-key install and its generation.
func (c *Cache) removeIfSame(key string, want *cachedPolicies) {
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

func validateLoadedPolicies(policies []Policy) ([]Policy, error) {
	out := make([]Policy, 0, len(policies))
	for _, p := range policies {
		if err := ValidatePattern(p.Pattern); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, nil
}

func clonePolicies(in []Policy) []Policy {
	if len(in) == 0 {
		return []Policy{}
	}
	out := make([]Policy, len(in))
	copy(out, in)
	return out
}

// gensLen reports generation-map size for tests.
func (c *Cache) gensLen() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.gens)
}
