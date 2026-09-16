package evidenceoutbox

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

// OutboxRow is one unpublished (or in-flight) evidence publication record.
type OutboxRow struct {
	ID             uuid.UUID
	OrgID          uuid.UUID
	EventID        uuid.UUID
	AggregateID    string
	AggregateSeq   int64
	SchemaVersion  string
	EventType      string
	Payload        json.RawMessage
	PayloadDigest  string
	DeliveryStatus string
	Attempts       int
	AvailableAt    time.Time
	LastError      string
	CreatedAt      time.Time
	DeliveredAt    *time.Time
}

// AssemblyMetrics is the durable stage-timing contract (mirrors proto AssemblyMetrics).
type AssemblyMetrics struct {
	BudgetCalculationMs   int
	DirectiveLoadMs       int
	HotMemoryRetrievalMs  int
	ColdMemoryRetrievalMs int
	RankingMs             int
	PackingMs             int
	FormattingMs          int
	TotalMs               int
	CandidatesEvaluated   int
}

// ScoreCandidate is one retrieval candidate with versioned score payload.
type ScoreCandidate struct {
	MemoryID        uuid.UUID
	RetrievalRank   int
	FinalRank       *int
	DeltaRank       *int
	Similarity      *float64
	Confidence      *float64
	CompositeScore  *float64
	ScoreSchema     string
	ScoreComponents map[string]float64
	Exclusion       string
	TokenEstimate   *int
	Category        string
}

// DirectiveSnapshot is the per-request directive version/hash provenance.
type DirectiveSnapshot struct {
	DirectiveVersionID *uuid.UUID
	ContentHash        string
}

// ToolAudit is a sanitized tool-call evidence row.
type ToolAudit struct {
	SpanID         string
	ToolName       string
	IdempotencyKey string
	SanitizedArgs  map[string]any
	Status         string
	ErrorCode      string
}

// SpanInput describes one nested span under a run.
type SpanInput struct {
	SpanID        string
	ParentSpanID  string
	OperationKind string
	Status        string
	ErrorCode     string
	Attributes    map[string]any
	StartedAt     time.Time
	EndedAt       time.Time
}

// SessionEventInput appends one session_events row (conversation / raw linkage).
type SessionEventInput struct {
	SessionID      uuid.UUID
	SequenceNumber int
	EventType      string
	Data           map[string]any
	ArchivedTo     string
}

// RunInput is the atomic evidence bundle written with matching outbox rows.
type RunInput struct {
	OrgID          uuid.UUID
	AgentID        *uuid.UUID
	SessionID      *uuid.UUID
	RequestID      string
	TraceID        string
	RootSpanID     string
	CheckpointID   *uuid.UUID
	TurnID         *int
	Completeness   string
	Status         string
	ErrorCode      string
	CaptureMode    string
	SampleDecision string
	StartedAt      time.Time
	EndedAt        time.Time
	Spans          []SpanInput
	Metrics        *AssemblyMetrics
	Candidates     []ScoreCandidate
	Directive      *DirectiveSnapshot
	Tools          []ToolAudit
	SessionEvents  []SessionEventInput
}

// PersistResult is the outcome of PersistRun (IDs for joins / tests).
type PersistResult struct {
	RunID       uuid.UUID
	OutboxIDs   []uuid.UUID
	AggregateID string
}
