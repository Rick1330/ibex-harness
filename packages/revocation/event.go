package revocation

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// Channel is the global Redis pub/sub channel for token revocation events.
const Channel = "ibex:token:revocations"

// CurrentSchemaVersion is the RevocationEvent.Version value for this release.
const CurrentSchemaVersion = 1

// RevocationEvent is published after a durable Postgres revoke.
// token_id (not SHA-256 of the bearer) is the invalidate key: RevokeToken has no
// raw token, and tokens.hash is Argon2id — not authcache.TokenHash.
type RevocationEvent struct {
	Version   int       `json:"v"`
	TokenID   string    `json:"token_id"`
	OrgID     string    `json:"org_id"`
	RevokedAt time.Time `json:"revoked_at"`
}

// Validate checks required fields for schema version 1.
func (e RevocationEvent) Validate() error {
	if e.Version != CurrentSchemaVersion {
		return fmt.Errorf("revocation: unsupported schema version %d", e.Version)
	}
	if strings.TrimSpace(e.TokenID) == "" {
		return fmt.Errorf("revocation: token_id is required")
	}
	return nil
}

// Marshal encodes the event as JSON for Redis PUBLISH.
func (e RevocationEvent) Marshal() ([]byte, error) {
	if err := e.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(e)
}

// ParseEvent decodes and validates a Redis pub/sub payload.
func ParseEvent(payload string) (RevocationEvent, error) {
	var e RevocationEvent
	if err := json.Unmarshal([]byte(payload), &e); err != nil {
		return RevocationEvent{}, fmt.Errorf("revocation: decode: %w", err)
	}
	if err := e.Validate(); err != nil {
		return RevocationEvent{}, err
	}
	return e, nil
}
