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

// Event type discriminators for RevocationEvent (ADR-0073).
const (
	EventTypeToken      = "token"
	EventTypeOrgSuspend = "org_suspend"
)

// RevocationEvent is published after a durable Postgres revoke or org suspension.
// token_id (not SHA-256 of the bearer) is the invalidate key for token events:
// RevokeToken has no raw token, and tokens.hash is Argon2id — not authcache.TokenHash.
//
// EventType discriminates token revocation vs org suspension (ADR-0073). When
// omitted (legacy publishers), EventType defaults to "token" on parse.
type RevocationEvent struct {
	Version   int       `json:"v"`
	EventType string    `json:"event_type,omitempty"`
	TokenID   string    `json:"token_id,omitempty"`
	OrgID     string    `json:"org_id"`
	RevokedAt time.Time `json:"revoked_at"`
}

// Validate checks required fields for schema version 1.
func (e RevocationEvent) Validate() error {
	if e.Version != CurrentSchemaVersion {
		return fmt.Errorf("revocation: unsupported schema version %d", e.Version)
	}
	eventType := e.normalizedEventType()
	if strings.TrimSpace(e.OrgID) == "" {
		return fmt.Errorf("revocation: org_id is required")
	}
	if e.RevokedAt.IsZero() {
		return fmt.Errorf("revocation: revoked_at is required")
	}
	switch eventType {
	case EventTypeToken:
		if strings.TrimSpace(e.TokenID) == "" {
			return fmt.Errorf("revocation: token_id is required")
		}
	case EventTypeOrgSuspend:
		// org_id already required; token_id optional/ignored.
	default:
		return fmt.Errorf("revocation: unsupported event_type %q", eventType)
	}
	return nil
}

func (e RevocationEvent) normalizedEventType() string {
	if strings.TrimSpace(e.EventType) == "" {
		return EventTypeToken
	}
	return strings.TrimSpace(e.EventType)
}

// EffectiveEventType returns the discriminator, defaulting missing values to token.
func (e RevocationEvent) EffectiveEventType() string {
	return e.normalizedEventType()
}

// Marshal encodes the event as JSON for Redis PUBLISH.
func (e RevocationEvent) Marshal() ([]byte, error) {
	if err := e.Validate(); err != nil {
		return nil, err
	}
	out := e
	if strings.TrimSpace(out.EventType) == "" {
		out.EventType = EventTypeToken
	}
	return json.Marshal(out)
}

// ParseEvent decodes and validates a Redis pub/sub payload.
// Legacy payloads without event_type are treated as token revocations.
func ParseEvent(payload string) (RevocationEvent, error) {
	var e RevocationEvent
	if err := json.Unmarshal([]byte(payload), &e); err != nil {
		return RevocationEvent{}, fmt.Errorf("revocation: decode: %w", err)
	}
	if strings.TrimSpace(e.EventType) == "" {
		e.EventType = EventTypeToken
	}
	if err := e.Validate(); err != nil {
		return RevocationEvent{}, err
	}
	return e, nil
}
