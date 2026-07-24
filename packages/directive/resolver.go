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
	Invalidate(orgID, agentID uuid.UUID)
}

// Store loads the active directive from durable storage.
type Store interface {
	Load(ctx context.Context, orgID, agentID uuid.UUID) (Resolved, error)
}

// NoopResolver always returns an empty Resolved (no directive).
type NoopResolver struct{}

// Resolve implements Resolver.
func (NoopResolver) Resolve(context.Context, uuid.UUID, uuid.UUID) (Resolved, error) {
	return Resolved{}, nil
}

// Invalidate implements Resolver.
func (NoopResolver) Invalidate(uuid.UUID, uuid.UUID) {}
