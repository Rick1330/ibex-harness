package modelpolicy

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	lru "github.com/hashicorp/golang-lru/v2"
)

type cachedPolicies struct {
	policies  []Policy
	expiresAt time.Time
}

// Cache is a bloom → LRU policy cache in front of PolicyLoader.
type Cache struct {
	loader  PolicyLoader
	cfg     Config
	metrics Metrics
	bloom   *policyBloom
	lru     *lru.Cache[string, *cachedPolicies]
	now     func() time.Time

	genMu sync.Mutex
	gens  map[string]uint64
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
		bloom:   newPolicyBloom(cfg.BloomExpected, cfg.BloomFPRate),
		now:     time.Now,
		gens:    make(map[string]uint64),
	}
	cache, err := lru.New[string, *cachedPolicies](cfg.LRUSize)
	if err != nil {
		return nil, fmt.Errorf("modelpolicy: lru: %w", err)
	}
	c.lru = cache
	return c, nil
}

// PoliciesForOrg returns cached or freshly loaded policies for orgID.
// LRU miss always loads from Postgres (fail-closed). Bloom is a positive hint
// only and never skips the loader — false negatives would fail open.
func (c *Cache) PoliciesForOrg(ctx context.Context, orgID uuid.UUID) ([]Policy, error) {
	key := orgID.String()
	if policies, ok := c.lookupFresh(key); ok {
		c.metrics.IncCacheHit("lru")
		return policies, nil
	}
	c.metrics.IncCacheMiss("lru")
	return c.loadAndStore(ctx, orgID, key)
}

func (c *Cache) lookupFresh(key string) ([]Policy, bool) {
	entry, ok := c.lru.Get(key)
	if !ok || entry == nil {
		return nil, false
	}
	if !c.now().Before(entry.expiresAt) {
		return nil, false
	}
	return clonePolicies(entry.policies), true
}

func (c *Cache) loadAndStore(ctx context.Context, orgID uuid.UUID, key string) ([]Policy, error) {
	// Touch bloom for metrics/observability only; never gate the load on it.
	_ = c.bloom.mayHave(key)

	gen := c.generation(key)
	policies, err := c.loader.LoadOrg(ctx, orgID)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrPolicyUnavailable, err)
	}
	if policies == nil {
		policies = []Policy{}
	}
	if len(policies) > 0 {
		c.bloom.add(key)
	}
	// Invalidate during LoadOrg must not re-cache stale rows.
	if c.generation(key) != gen {
		return clonePolicies(policies), nil
	}
	c.lru.Add(key, &cachedPolicies{
		policies:  clonePolicies(policies),
		expiresAt: c.now().Add(c.cfg.CacheTTL),
	})
	c.metrics.SetLRUSize(float64(c.lru.Len()))
	return clonePolicies(policies), nil
}

func (c *Cache) generation(key string) uint64 {
	c.genMu.Lock()
	defer c.genMu.Unlock()
	return c.gens[key]
}

func (c *Cache) bumpGeneration(key string) {
	c.genMu.Lock()
	defer c.genMu.Unlock()
	c.gens[key]++
}

// Invalidate drops the LRU entry for orgID and advances its generation.
func (c *Cache) Invalidate(orgID uuid.UUID) {
	if orgID == uuid.Nil {
		return
	}
	key := orgID.String()
	c.bumpGeneration(key)
	c.lru.Remove(key)
	c.metrics.IncInvalidate()
	c.metrics.SetLRUSize(float64(c.lru.Len()))
}

func clonePolicies(in []Policy) []Policy {
	if len(in) == 0 {
		return []Policy{}
	}
	out := make([]Policy, len(in))
	copy(out, in)
	return out
}
