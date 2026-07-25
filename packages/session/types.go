package session

import "github.com/google/uuid"

// Session status values stored in ibex_core.sessions.status.
const (
	StatusActive    = "active"
	StatusCompleted = "completed"
	StatusAbandoned = "abandoned"
	StatusError     = "error"
)

// Session is a row from ibex_core.sessions returned to callers.
type Session struct {
	ID                 uuid.UUID
	OrgID              uuid.UUID
	AgentID            uuid.UUID
	ExternalID         *string
	Status             string
	Model              string
	Provider           string
	DirectiveVersionID *uuid.UUID
	TurnCount          int
	TotalInputTokens   int64
	TotalOutputTokens  int64
	TotalLatencyMs     int64
}

// GetOrCreateParams creates or looks up a session for an org/agent.
type GetOrCreateParams struct {
	OrgID              uuid.UUID
	AgentID            uuid.UUID
	ExternalID         string // optional; from X-IBEX-Session-ID
	Model              string
	Provider           string
	DirectiveVersionID *uuid.UUID
}

// CheckpointParams records one immutable turn and updates session aggregates.
type CheckpointParams struct {
	SessionID         uuid.UUID
	OrgID             uuid.UUID
	AgentID           uuid.UUID
	TurnIndex         int
	RequestID         string
	MessagesHash      string
	InputTokens       int
	OutputTokens      int
	Model             string
	Provider          string
	CompletionHash    string
	LatencyMs         int
	ProviderRequestID string
	IsStreaming       bool
	IsComplete        bool
}
