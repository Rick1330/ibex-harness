// Package sessioncache provides a thin Redis cache for session hot-path state.
// Postgres remains the source of truth; Redis failures fail open to the store.
package sessioncache

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// Entry is the cached session identity used to skip Postgres on hit.
type Entry struct {
	SessionID uuid.UUID `json:"session_id"`
	TurnCount int       `json:"turn_count"`
}

// Cache stores org-scoped session lookups in Redis.
type Cache struct {
	client redis.UniversalClient
	ttl    time.Duration
}

// New returns a Cache. client must be non-nil; ttl must be > 0.
func New(client redis.UniversalClient, ttl time.Duration) (*Cache, error) {
	if client == nil {
		return nil, fmt.Errorf("sessioncache: redis client is required")
	}
	if ttl <= 0 {
		return nil, fmt.Errorf("sessioncache: ttl must be > 0")
	}
	return &Cache{client: client, ttl: ttl}, nil
}

// KeyFormat is {org_id}:session:{agent_id}:{external_id}.
func Key(orgID, agentID uuid.UUID, externalID string) string {
	return fmt.Sprintf("%s:session:%s:%s", orgID.String(), agentID.String(), externalID)
}

// Get returns a cache entry on hit. Miss, corrupt payload, or Redis errors
// return ok=false (fail-open).
func (c *Cache) Get(ctx context.Context, orgID, agentID uuid.UUID, externalID string) (Entry, bool) {
	if c == nil || externalID == "" {
		return Entry{}, false
	}
	raw, err := c.client.Get(ctx, Key(orgID, agentID, externalID)).Bytes()
	if err != nil {
		return Entry{}, false
	}
	var e Entry
	if err := json.Unmarshal(raw, &e); err != nil {
		return Entry{}, false
	}
	if e.SessionID == uuid.Nil {
		return Entry{}, false
	}
	return e, true
}

// Set stores entry best-effort. Redis errors are ignored (fail-open).
func (c *Cache) Set(ctx context.Context, orgID, agentID uuid.UUID, externalID string, e Entry) {
	if c == nil || externalID == "" || e.SessionID == uuid.Nil {
		return
	}
	payload, err := json.Marshal(e)
	if err != nil {
		return
	}
	_ = c.client.Set(ctx, Key(orgID, agentID, externalID), payload, c.ttl).Err()
}

// Invalidate deletes a cache key best-effort (e.g. after ErrDuplicateTurn).
func (c *Cache) Invalidate(ctx context.Context, orgID, agentID uuid.UUID, externalID string) {
	if c == nil || externalID == "" {
		return
	}
	_ = c.client.Del(ctx, Key(orgID, agentID, externalID)).Err()
}
