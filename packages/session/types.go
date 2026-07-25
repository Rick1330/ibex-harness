package session

import (
	"time"

	"github.com/google/uuid"
)

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

// AbandonIdleParams selects active sessions idle before IdleBefore (exclusive).
type AbandonIdleParams struct {
	IdleBefore time.Time
	Limit      int
}

// AbandonedSession is one row marked abandoned by AbandonIdle.
type AbandonedSession struct {
	SessionID  uuid.UUID
	OrgID      uuid.UUID
	AgentID    uuid.UUID
	ExternalID *string
}

// AbandonIdleResult is the outcome of a sweeper batch.
type AbandonIdleResult struct {
	Abandoned   []AbandonedSession
	SkippedLock bool
}

// Count returns how many sessions were abandoned in this batch.
func (r AbandonIdleResult) Count() int {
	return len(r.Abandoned)
}
