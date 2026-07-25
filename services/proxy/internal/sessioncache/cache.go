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

// EntryVersion is the JSON schema version for cached session payloads.
const EntryVersion = 1

// Entry is the cached session identity used to skip Postgres on hit.
type Entry struct {
	Version   int       `json:"v"`
	SessionID uuid.UUID `json:"session_id"`
	TurnCount int       `json:"turn_count"`
}

// LookupKey identifies a tenant-scoped session sticky key in Redis.
type LookupKey struct {
	OrgID      uuid.UUID
	AgentID    uuid.UUID
	ExternalID string
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

// Key returns session:{org_id}:{agent_id}:{external_id} (org_id is the second segment).
func Key(k LookupKey) string {
	return fmt.Sprintf("session:%s:%s:%s", k.OrgID.String(), k.AgentID.String(), k.ExternalID)
}

// Get returns a cache entry on hit. Miss, corrupt payload, version mismatch, or
// Redis errors return ok=false (fail-open).
func (c *Cache) Get(ctx context.Context, k LookupKey) (Entry, bool) {
	if c == nil || k.ExternalID == "" {
		return Entry{}, false
	}
	raw, err := c.client.Get(ctx, Key(k)).Bytes()
	if err != nil {
		return Entry{}, false
	}
	var e Entry
	if err := json.Unmarshal(raw, &e); err != nil {
		return Entry{}, false
	}
	if !e.valid() {
		return Entry{}, false
	}
	return e, true
}

func (e Entry) valid() bool {
	if e.SessionID == uuid.Nil {
		return false
	}
	// Accept legacy payloads that omitted v (treated as current).
	if e.Version == 0 {
		return true
	}
	return e.Version == EntryVersion
}

// Set stores entry best-effort. Redis errors are ignored (fail-open).
func (c *Cache) Set(ctx context.Context, k LookupKey, e Entry) {
	if !c.canWrite(k, e) {
		return
	}
	if e.Version == 0 {
		e.Version = EntryVersion
	}
	payload, err := json.Marshal(e)
	if err != nil {
		return
	}
	_ = c.client.Set(ctx, Key(k), payload, c.ttl).Err()
}

func (c *Cache) canWrite(k LookupKey, e Entry) bool {
	if c == nil {
		return false
	}
	if k.ExternalID == "" {
		return false
	}
	return e.SessionID != uuid.Nil
}

// Invalidate deletes a cache key best-effort (e.g. after ErrDuplicateTurn).
func (c *Cache) Invalidate(ctx context.Context, k LookupKey) {
	if c == nil || k.ExternalID == "" {
		return
	}
	_ = c.client.Del(ctx, Key(k)).Err()
}
