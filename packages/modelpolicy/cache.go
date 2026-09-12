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
	expiresAt time.Time
	gen       uint64
}

// Cache is a process-local LRU + TTL policy cache in front of PolicyLoader.
// Invalidate advances a per-org generation under the same lock used for install,
// so in-flight loads cannot repopulate a stale snapshot (ADR-0075 fail-closed).
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
	cache, err := lru.New[string, *cachedPolicies](cfg.LRUSize)
	if err != nil {
		return nil, fmt.Errorf("modelpolicy: lru: %w", err)
	}
	c.lru = cache
	return c, nil
}

// PoliciesForOrg returns cached or freshly loaded policies for orgID.
// Loader errors and invalid patterns fail closed.
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
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.lru.Get(key)
	if !ok || entry == nil {
		return nil, false
	}
	if entry.gen != c.gens[key] {
		c.lru.Remove(key)
		return nil, false
	}
	if !c.now().Before(entry.expiresAt) {
		c.lru.Remove(key)
		return nil, false
	}
	return clonePolicies(entry.policies), true
}

func (c *Cache) loadAndStore(ctx context.Context, orgID uuid.UUID, key string) ([]Policy, error) {
	loadCtx := ctx
	if c.cfg.LoadTimeout > 0 {
		var cancel context.CancelFunc
		loadCtx, cancel = context.WithTimeout(ctx, c.cfg.LoadTimeout)
		defer cancel()
	}
	for attempt := 0; attempt < maxPolicyLoadAttempts; attempt++ {
		policies, ok, err := c.loadOnce(loadCtx, orgID, key)
		if err != nil {
			return nil, err
		}
		if ok {
			return policies, nil
		}
	}
	return nil, fmt.Errorf("%w: invalidated during load", ErrPolicyUnavailable)
}

func (c *Cache) loadOnce(ctx context.Context, orgID uuid.UUID, key string) ([]Policy, bool, error) {
	c.mu.Lock()
	gen := c.gens[key]
	c.mu.Unlock()

	policies, err := c.loader.LoadOrg(ctx, orgID)
	if err != nil {
		return nil, false, fmt.Errorf("%w: %w", ErrPolicyUnavailable, err)
	}
	if policies == nil {
		policies = []Policy{}
	}
	policies, err = validateLoadedPolicies(policies)
	if err != nil {
		return nil, false, fmt.Errorf("%w: %w", ErrPolicyUnavailable, err)
	}

	c.mu.Lock()
	defer c.mu.Unlock()
	if c.gens[key] != gen {
		// Stale snapshot — do not cache or return; caller retries.
		return nil, false, nil
	}
	c.lru.Add(key, &cachedPolicies{
		policies:  clonePolicies(policies),
		expiresAt: c.now().Add(c.cfg.CacheTTL),
		gen:       gen,
	})
	c.metrics.SetLRUSize(float64(c.lru.Len()))
	return clonePolicies(policies), true, nil
}

// Invalidate drops the LRU entry for orgID and advances its generation.
func (c *Cache) Invalidate(orgID uuid.UUID) {
	if orgID == uuid.Nil {
		return
	}
	key := orgID.String()
	c.mu.Lock()
	c.gens[key]++
	c.lru.Remove(key)
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
