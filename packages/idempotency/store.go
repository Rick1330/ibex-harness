// Package idempotency provides Redis-backed claim/commit for request dedupe.
package idempotency

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// Kind is the outcome of a Claim.
type Kind int

const (
	// KindMiss means this caller owns the in-flight claim.
	KindMiss Kind = iota
	// KindHit means a completed response is available for replay.
	KindHit
	// KindConflict means the key was used with a different request fingerprint.
	KindConflict
	// KindInProgress means another request holds the pending claim.
	KindInProgress
)

// State is the durable Redis record state.
type State string

const (
	// StatePending is set while the first request is still calling the provider.
	StatePending State = "pending"
	// StateCompleted is set after a terminal response was written to the client.
	StateCompleted State = "completed"
)

// Record is the Redis value for an idempotency key.
type Record struct {
	State       State  `json:"state"`
	Fingerprint string `json:"fp"`
	Status      int    `json:"status,omitempty"`
	Body        []byte `json:"body,omitempty"`
}

// Outcome is returned by Claim.
type Outcome struct {
	Kind   Kind
	Record Record
}

// Store claims and commits org-scoped idempotency keys.
type Store interface {
	// Claim reserves or inspects the key for orgID.
	// A non-nil error is an infrastructure failure (caller should fail-open).
	Claim(ctx context.Context, orgID uuid.UUID, key, fingerprint string) (Outcome, error)
	// Commit stores a completed record over a pending claim (same fingerprint).
	Commit(ctx context.Context, orgID uuid.UUID, key string, rec Record) error
}

type noopStore struct{}

func (noopStore) Claim(_ context.Context, _ uuid.UUID, _, _ string) (Outcome, error) {
	return Outcome{Kind: KindMiss}, nil
}

func (noopStore) Commit(_ context.Context, _ uuid.UUID, _ string, _ Record) error {
	return nil
}

// Noop returns a store that always reports Miss and ignores Commit (tests / disabled).
func Noop() Store {
	return noopStore{}
}

// Config configures the Redis-backed store.
type Config struct {
	TTL time.Duration
}

const defaultTTL = 24 * time.Hour
