package trace

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

// RequestTimings holds proxy-measured stage and wall-clock latencies.
type RequestTimings struct {
	AuthMs       uint16
	DirectiveMs  uint16
	ProviderTTFB time.Duration
	RequestedAt  time.Time
	CompletedAt  time.Time
}

// RequestOutcome is the HTTP/completion result for a trace row.
type RequestOutcome struct {
	StatusCode uint16
	IsComplete bool
	ErrorCode  string
	// StreamRequested is the client stream flag when checkpoint IsStreaming
	// must stay false (e.g. provider failure before a stream body starts).
	StreamRequested bool
}

// AssembleInput is the immutable snapshot for Assemble (≤4 logical groups).
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
