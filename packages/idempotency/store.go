// Package idempotency provides Redis-backed claim/commit for request dedupe.
package idempotency

import (
	"context"
	"fmt"
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

// CurrentRecordVersion is the JSON schema version written by this package.
const CurrentRecordVersion = 1

// Token identifies an org-scoped idempotency key.
type Token struct {
	OrgID uuid.UUID
	Key   string
}

// Fingerprint is the normalized request fingerprint bound to an idempotency key.
type Fingerprint string

// Record is the Redis value for an idempotency key.
type Record struct {
	Version     int         `json:"v"`
	State       State       `json:"state"`
	Fingerprint Fingerprint `json:"fp"`
	Status      int         `json:"status,omitempty"`
	Body        []byte      `json:"body,omitempty"`
}

// Outcome is returned by Claim.
type Outcome struct {
	Kind   Kind
	Record Record
}

// Store claims and commits org-scoped idempotency keys.
type Store interface {
	// Claim reserves or inspects the key for tok.
	// A non-nil error is an infrastructure failure (caller should fail-open).
	Claim(ctx context.Context, tok Token, fingerprint Fingerprint) (Outcome, error)
	// Commit stores a completed record only when the key is still pending with the same fingerprint.
	Commit(ctx context.Context, tok Token, rec Record) error
	// Release deletes a pending claim with matching fingerprint so a later retry can reclaim.
	Release(ctx context.Context, tok Token, fingerprint Fingerprint) error
}

type noopStore struct{}

func (noopStore) Claim(_ context.Context, _ Token, _ Fingerprint) (Outcome, error) {
	return Outcome{Kind: KindMiss}, nil
}

func (noopStore) Commit(_ context.Context, _ Token, _ Record) error {
	return nil
}

func (noopStore) Release(_ context.Context, _ Token, _ Fingerprint) error {
	return nil
}

// Noop returns a store that always reports Miss and ignores Commit/Release.
func Noop() Store {
	return noopStore{}
}

// Config configures the Redis-backed store.
type Config struct {
	TTL        time.Duration // completed-record TTL (default 24h)
	PendingTTL time.Duration // in-flight claim TTL (default 9m)
}

const (
	defaultTTL = 24 * time.Hour
	// defaultPendingTTL covers worst-case OpenAI Complete with retries:
	// RequestTimeout 120s × (MaxRetries 3 + 1) plus backoff headroom.
	defaultPendingTTL = 9 * time.Minute
)

func (c Config) withDefaults() Config {
	if c.TTL <= 0 {
		c.TTL = defaultTTL
	}
	if c.PendingTTL <= 0 {
		c.PendingTTL = defaultPendingTTL
	}
	return c
}

// ErrUnsupportedVersion is returned when a Redis value has an unknown schema version.
var ErrUnsupportedVersion = fmt.Errorf("idempotency: unsupported record version")

// RedisKey returns the org-scoped Redis key for tok.
// Format: idempotency:{org_id}:{key}
func RedisKey(tok Token) string {
	return fmt.Sprintf("idempotency:%s:%s", tok.OrgID.String(), tok.Key)
}
