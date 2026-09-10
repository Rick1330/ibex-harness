package ratelimit

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// ConfigEventVersion is ConfigUpdateEvent.Version for this release.
const ConfigEventVersion = 1

// ConfigUpdateEvent is published when org/agent RPM overrides change.
// Channel is ratelimit_config_updates:{org_id}; payload is invalidate-only
// (proxy reloads from Postgres — pub/sub is not source of truth).
type ConfigUpdateEvent struct {
	Version int    `json:"v"`
	OrgID   string `json:"org_id"`
}

// Validate checks required fields for schema version 1.
func (e ConfigUpdateEvent) Validate() error {
	if e.Version != ConfigEventVersion {
		return fmt.Errorf("ratelimit: unsupported config event version %d", e.Version)
	}
	if strings.TrimSpace(e.OrgID) == "" {
		return fmt.Errorf("ratelimit: org_id is required")
	}
	if _, err := uuid.Parse(e.OrgID); err != nil {
		return fmt.Errorf("ratelimit: org_id: %w", err)
	}
	return nil
}

// Marshal encodes the event as JSON for Redis PUBLISH after Validate.
func (e ConfigUpdateEvent) Marshal() ([]byte, error) {
	if err := e.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(e)
}

// ParseConfigUpdateEvent decodes and validates a Redis pub/sub payload.
func ParseConfigUpdateEvent(payload string) (ConfigUpdateEvent, error) {
	var e ConfigUpdateEvent
	if err := json.Unmarshal([]byte(payload), &e); err != nil {
		return ConfigUpdateEvent{}, fmt.Errorf("ratelimit: decode config event: %w", err)
	}
	if err := e.Validate(); err != nil {
		return ConfigUpdateEvent{}, err
	}
	return e, nil
}
