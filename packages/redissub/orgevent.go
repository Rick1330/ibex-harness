package redissub

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// OrgInvalidateEvent is the shared JSON payload for org-scoped cache invalidation.
type OrgInvalidateEvent struct {
	Version int    `json:"v"`
	OrgID   string `json:"org_id"`
	Epoch   uint64 `json:"epoch,omitempty"`
}

// EventPolicy configures Validate rules for a domain.
type EventPolicy struct {
	ErrPrefix      string
	CurrentVersion int
	RequireEpoch   bool
}

// Validate checks version, org_id, and optional epoch.
func (e OrgInvalidateEvent) Validate(p EventPolicy) error {
	prefix := p.ErrPrefix
	if prefix == "" {
		prefix = "redissub"
	}
	if e.Version != p.CurrentVersion {
		return fmt.Errorf("%s: unsupported event version %d", prefix, e.Version)
	}
	if strings.TrimSpace(e.OrgID) == "" {
		return fmt.Errorf("%s: org_id is required", prefix)
	}
	if _, err := uuid.Parse(e.OrgID); err != nil {
		return fmt.Errorf("%s: org_id: %w", prefix, err)
	}
	if p.RequireEpoch && e.Epoch < 1 {
		return fmt.Errorf("%s: epoch must be >= 1", prefix)
	}
	return nil
}

// MarshalOrgEvent validates then encodes JSON.
func MarshalOrgEvent(e OrgInvalidateEvent, p EventPolicy) ([]byte, error) {
	if err := e.Validate(p); err != nil {
		return nil, err
	}
	return json.Marshal(e)
}

// ParseOrgEvent decodes and validates a Redis pub/sub payload.
func ParseOrgEvent(payload string, p EventPolicy) (OrgInvalidateEvent, error) {
	prefix := p.ErrPrefix
	if prefix == "" {
		prefix = "redissub"
	}
	var e OrgInvalidateEvent
	if err := json.Unmarshal([]byte(payload), &e); err != nil {
		return OrgInvalidateEvent{}, fmt.Errorf("%s: decode event: %w", prefix, err)
	}
	if err := e.Validate(p); err != nil {
		return OrgInvalidateEvent{}, err
	}
	return e, nil
}
