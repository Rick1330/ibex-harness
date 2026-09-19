package modelpolicy

import (
	"github.com/Rick1330/ibex-harness/packages/redissub"
)

// InvalidateEvent is published when org model policies change.
type InvalidateEvent struct {
	Version int    `json:"v"`
	OrgID   string `json:"org_id"`
	Epoch   uint64 `json:"epoch"`
}

func (e InvalidateEvent) toShared() redissub.OrgInvalidateEvent {
	return redissub.OrgInvalidateEvent{Version: e.Version, OrgID: e.OrgID, Epoch: e.Epoch}
}

func fromShared(e redissub.OrgInvalidateEvent) InvalidateEvent {
	return InvalidateEvent{Version: e.Version, OrgID: e.OrgID, Epoch: e.Epoch}
}

// Validate checks required fields for schema version 1.
func (e InvalidateEvent) Validate() error {
	return e.toShared().Validate(eventPolicy)
}

// Marshal encodes the event as JSON after Validate.
func (e InvalidateEvent) Marshal() ([]byte, error) {
	return redissub.MarshalOrgEvent(e.toShared(), eventPolicy)
}

// ParseInvalidateEvent decodes and validates a Redis pub/sub payload.
func ParseInvalidateEvent(payload string) (InvalidateEvent, error) {
	e, err := redissub.ParseOrgEvent(payload, eventPolicy)
	if err != nil {
		return InvalidateEvent{}, err
	}
	return fromShared(e), nil
}
