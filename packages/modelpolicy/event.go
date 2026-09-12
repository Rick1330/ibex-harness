package modelpolicy

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// InvalidateEvent is published when org model policies change.
type InvalidateEvent struct {
	Version int    `json:"v"`
	OrgID   string `json:"org_id"`
}

// Validate checks required fields for schema version 1.
func (e InvalidateEvent) Validate() error {
	if e.Version != CurrentEventVersion {
		return fmt.Errorf("modelpolicy: unsupported event version %d", e.Version)
	}
	if strings.TrimSpace(e.OrgID) == "" {
		return fmt.Errorf("modelpolicy: org_id is required")
	}
	if _, err := uuid.Parse(e.OrgID); err != nil {
		return fmt.Errorf("modelpolicy: org_id: %w", err)
	}
	return nil
}

// Marshal encodes the event as JSON after Validate.
func (e InvalidateEvent) Marshal() ([]byte, error) {
	if err := e.Validate(); err != nil {
		return nil, err
	}
	return json.Marshal(e)
}

// ParseInvalidateEvent decodes and validates a Redis pub/sub payload.
func ParseInvalidateEvent(payload string) (InvalidateEvent, error) {
	var e InvalidateEvent
	if err := json.Unmarshal([]byte(payload), &e); err != nil {
		return InvalidateEvent{}, fmt.Errorf("modelpolicy: decode event: %w", err)
	}
	if err := e.Validate(); err != nil {
		return InvalidateEvent{}, err
	}
	return e, nil
}
