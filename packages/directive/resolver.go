// Package directive provides directive resolution for the proxy hot path.
package directive

import (
	"context"

	"github.com/google/uuid"
)

// Resolved is the active directive payload for an agent.
// Empty Content means the agent has no active directive.
type Resolved struct {
	Content       string
	InjectionMode string
	VersionID     uuid.UUID
}

// HasContent reports whether a non-empty directive was resolved.
func (r Resolved) HasContent() bool {
	return r.Content != ""
}

// Resolver resolves the active directive for an agent.
// Returns a zero Resolved (empty Content) when the agent has no active directive.
// Returns an error only for infrastructure failures (DB/Redis down).
type Resolver interface {
	Resolve(ctx context.Context, orgID, agentID uuid.UUID) (Resolved, error)
	Invalidate(ctx context.Context, orgID, agentID uuid.UUID)
}

// Loader loads the active directive from durable storage.
type Loader interface {
	Load(ctx context.Context, orgID, agentID uuid.UUID) (Resolved, error)
}

// NoopResolver always returns an empty Resolved (no directive).
// Used when POSTGRES_DSN or REDIS_URL is unset so chat continues without injection.
type NoopResolver struct{}

// Resolve returns empty content without consulting Redis or Postgres.
// Intentionally a no-op: represents "directive resolution disabled".
func (NoopResolver) Resolve(context.Context, uuid.UUID, uuid.UUID) (Resolved, error) {
	return Resolved{}, nil
}

// Invalidate is a no-op because NoopResolver holds no cache entries.
func (NoopResolver) Invalidate(context.Context, uuid.UUID, uuid.UUID) {
	// No-op: resolution disabled — nothing to invalidate.
}
