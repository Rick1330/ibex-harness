package billing

import "github.com/Rick1330/ibex-harness/packages/redissub"

// InvalidateEvent is the budget-cache invalidate payload (shared JSON schema).
type InvalidateEvent = redissub.OrgInvalidateEvent

// ParseInvalidateEvent decodes and validates a Redis pub/sub payload.
func ParseInvalidateEvent(payload string) (InvalidateEvent, error) {
	return redissub.ParseOrgEvent(payload, eventPolicy)
}

// MarshalInvalidate encodes a validated invalidate event as JSON.
func MarshalInvalidate(e InvalidateEvent) ([]byte, error) {
	return redissub.MarshalOrgEvent(e, eventPolicy)
}
