package directive

import (
	"encoding/json"
	"fmt"
	"strings"
)

// CurrentEventVersion is the UpdateEvent.Version value for this release.
const CurrentEventVersion = 1

// UpdateEvent is published when an agent's active directive changes.
type UpdateEvent struct {
	Version      int    `json:"v"`
	OrgID        string `json:"org_id"`
	AgentID      string `json:"agent_id"`
	NewVersionID string `json:"new_version_id"`
}

// Validate checks required fields for schema version 1.
func (e UpdateEvent) Validate() error {
	if e.Version != CurrentEventVersion {
		return fmt.Errorf("directive: unsupported event version %d", e.Version)
	}
	if strings.TrimSpace(e.OrgID) == "" {
		return fmt.Errorf("directive: org_id is required")
	}
	if strings.TrimSpace(e.AgentID) == "" {
		return fmt.Errorf("directive: agent_id is required")
	}
	return nil
}

// Marshal encodes the event as JSON for Redis PUBLISH.
func (e UpdateEvent) Marshal() ([]byte, error) {
	if err := e.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(e)
}

// ParseUpdateEvent decodes and validates a Redis pub/sub payload.
func ParseUpdateEvent(payload string) (UpdateEvent, error) {
	var e UpdateEvent
	if err := json.Unmarshal([]byte(payload), &e); err != nil {
		return UpdateEvent{}, fmt.Errorf("directive: decode event: %w", err)
	}
	if err := e.Validate(); err != nil {
		return UpdateEvent{}, err
	}
	return e, nil
}
