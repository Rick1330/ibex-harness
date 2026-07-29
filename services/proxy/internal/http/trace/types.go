package trace

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

// RequestTimings holds proxy-measured stage and wall-clock latencies.
// Zero RequestedAt/CompletedAt are filled by Assemble so callers need not
// invent clocks on early-exit paths.
type RequestTimings struct {
	AuthMs       uint16
	DirectiveMs  uint16
	ProviderTTFB time.Duration
	RequestedAt  time.Time
	CompletedAt  time.Time
}

// RequestOutcome is the HTTP/completion result for a trace row.
// StreamRequested lets failure paths mark streaming without appending a checkpoint.
type RequestOutcome struct {
	StatusCode uint16
	IsComplete bool
	ErrorCode  string
	// StreamRequested is the client stream flag when checkpoint IsStreaming
	// must stay false (e.g. provider failure before a stream body starts).
	StreamRequested bool
}

// AssembleInput is the immutable snapshot for Assemble.
// RequestID, OrgID, and AgentID are required identity; SessionID/Usage are optional.
// Prompt and completion content are intentionally omitted for privacy.
type AssembleInput struct {
	RequestID string
	OrgID     uuid.UUID
	AgentID   uuid.UUID
	SessionID *uuid.UUID
	Model     string
	Provider  string
	Streaming bool
	Usage     *provider.Usage
	Timings   RequestTimings
	Outcome   RequestOutcome
}
