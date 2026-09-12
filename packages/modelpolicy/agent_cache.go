package modelpolicy

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	lru "github.com/hashicorp/golang-lru/v2"
	"golang.org/x/sync/singleflight"
)

type cachedAgentDefaults struct {
	defaults  AgentDefaults
	expiresAt time.Time
}

// CachingAgentDefaults wraps an AgentDefaultLoader with a process-local LRU+TTL.
// Concurrent cold loads for the same org|agent key coalesce via singleflight.
type CachingAgentDefaults struct {
	inner AgentDefaultLoader
	cfg   Config
	lru   *lru.Cache[string, *cachedAgentDefaults]
	now   func() time.Time
	mu    sync.Mutex
	group singleflight.Group
}

// NewCachingAgentDefaults constructs a caching loader. inner is required.
func NewCachingAgentDefaults(inner AgentDefaultLoader, cfg Config) (*CachingAgentDefaults, error) {
	if inner == nil {
		return nil, fmt.Errorf("modelpolicy: agent defaults loader is required")
	}
	cfg.ApplyDefaults()
	cache, err := lru.New[string, *cachedAgentDefaults](cfg.AgentDefaultsLRU)
	if err != nil {
		return nil, fmt.Errorf("modelpolicy: agent defaults lru: %w", err)
	}
	return &CachingAgentDefaults{
		inner: inner,
		cfg:   cfg,
		lru:   cache,
		now:   time.Now,
	}, nil
}

// Load returns cached or freshly loaded agent defaults.
func (c *CachingAgentDefaults) Load(ctx context.Context, orgID, agentID uuid.UUID) (AgentDefaults, error) {
	key := orgID.String() + "|" + agentID.String()
	if d, ok := c.lookupFresh(key); ok {
		return d, nil
	}
	// Detach cancel/deadline from the shared flight so one abandoned request
	// cannot fail coalesced waiters. Callers still observe their own ctx via DoChan.
	loadParent := context.WithoutCancel(ctx)
	ch := c.group.DoChan(key, func() (any, error) {
		if d, ok := c.lookupFresh(key); ok {
			return d, nil
		}
		return c.loadAndStore(loadParent, key, orgID, agentID)
	})
	select {
	case <-ctx.Done():
		return AgentDefaults{}, ctx.Err()
	case res := <-ch:
		if res.Err != nil {
			return AgentDefaults{}, res.Err
		}
		return res.Val.(AgentDefaults), nil
	}
}

func (c *CachingAgentDefaults) loadAndStore(
	ctx context.Context, key string, orgID, agentID uuid.UUID,
) (AgentDefaults, error) {
	loadCtx := ctx
	if c.cfg.LoadTimeout > 0 {
		var cancel context.CancelFunc
		loadCtx, cancel = context.WithTimeout(ctx, c.cfg.LoadTimeout)
		defer cancel()
	}
	defaults, err := c.inner.Load(loadCtx, orgID, agentID)
	if err != nil {
		return AgentDefaults{}, err
	}
	c.mu.Lock()
	c.lru.Add(key, &cachedAgentDefaults{
		defaults:  defaults,
		expiresAt: c.now().Add(c.cfg.AgentDefaultsTTL),
	})
	c.mu.Unlock()
	return defaults, nil
}

func (c *CachingAgentDefaults) lookupFresh(key string) (AgentDefaults, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.lru.Get(key)
	if !ok || entry == nil {
		return AgentDefaults{}, false
	}
	if !c.now().Before(entry.expiresAt) {
		c.lru.Remove(key)
		return AgentDefaults{}, false
	}
	return entry.defaults, true
}
