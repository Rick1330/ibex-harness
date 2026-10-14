package evidenceoutbox

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// RedactionClass is the producer-assigned privacy class of an outbox payload.
type RedactionClass string

const (
	RedactionClassUnclassified RedactionClass = "unclassified"
	RedactionClassMetadata     RedactionClass = "metadata"
	RedactionClassRedacted     RedactionClass = "redacted"
	RedactionClassProhibited   RedactionClass = "prohibited"
)

func isSupportedRedactionClass(class RedactionClass) bool {
	switch class {
	case RedactionClassUnclassified, RedactionClassMetadata, RedactionClassRedacted, RedactionClassProhibited:
		return true
	default:
		return false
	}
}

// TombstoneFence identifies the authoritative resource version that a sink must
// check against the org-scoped PostgreSQL lifecycle record before projection.
type TombstoneFence struct {
	ResourceType    string `json:"resource_type"`
	ResourceID      string `json:"resource_id"`
	ResourceVersion int64  `json:"resource_version"`
}

// ProducerMetadata is the producer's explicit proof that an evidence payload
// was classified and bound to an authoritative resource lifecycle record.
// Empty or incomplete metadata is rejected when attached to a RunInput; the
// relay never infers these values from an untyped payload or aggregate ID.
type ProducerMetadata struct {
	RedactionClass        RedactionClass `json:"redaction_class"`
	RedactionProofVersion string         `json:"redaction_proof_version"`
	ResourceType          string         `json:"resource_type"`
	ResourceID            string         `json:"resource_id"`
	ResourceVersion       int64          `json:"resource_version"`
	Source                string         `json:"source"`
}

func validateProducerMetadata(metadata *ProducerMetadata) error {
	if metadata == nil {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if !isSupportedRedactionClass(metadata.RedactionClass) {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if metadata.RedactionClass == RedactionClassUnclassified {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if metadata.RedactionProofVersion == "" {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if metadata.ResourceType == "" {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if metadata.ResourceID == "" {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if metadata.ResourceVersion <= 0 {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	if metadata.Source == "" {
		return fmt.Errorf("evidenceoutbox: producer metadata is incomplete")
	}
	return nil
}

// OutboxRow is one unpublished (or in-flight) evidence publication record.
type OutboxRow struct {
	ID                  uuid.UUID
	OrgID               uuid.UUID
	EventID             uuid.UUID
	AggregateID         string
	AggregateSeq        int64
	SchemaVersion       string
	EventType           string
	RedactionClass      RedactionClass
	TombstoneFence      *TombstoneFence
	Payload             json.RawMessage
	PayloadDigestScheme string
	PayloadDigest       string
	DeliveryStatus      string
	Attempts            int
	AvailableAt         time.Time
	LastError           string
	CreatedAt           time.Time
	DeliveredAt         *time.Time
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

// TokenUsage contains numeric provider token totals only; prompts and response bodies are excluded.
type TokenUsage struct {
	InputTokens  int64 `json:"input_tokens"`
	OutputTokens int64 `json:"output_tokens"`
	TotalTokens  int64 `json:"total_tokens"`
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
	MetricsSpanID  string // optional; assembly metrics join key (prefer assemble span)
	CheckpointID   *uuid.UUID
	TurnID         *int
	ModelID        string
	TokenUsage     *TokenUsage
	Completeness   string
	Status         string
	ErrorCode      string
	CaptureMode    string
	SampleDecision string
	// RedactionClass must reflect the producer's sanitization result. Empty means
	// unclassified and is rejected by the relay; it is never upgraded implicitly.
	RedactionClass RedactionClass
	TombstoneFence *TombstoneFence
	Producer       *ProducerMetadata
	StartedAt      time.Time
	EndedAt        time.Time
	Spans          []SpanInput
	Metrics        *AssemblyMetrics
	Candidates     []ScoreCandidate
	Directive      *DirectiveSnapshot
	Tools          []ToolAudit
	SessionEvents  []SessionEventInput
	// DeployImageDigest is the OCI digest of the service binary that wrote this
	// bundle (4.P.5). Empty means unset / pre-4.P.5 writers.
	DeployImageDigest string
}

// PersistResult is the outcome of PersistRun (IDs for joins / tests).
type PersistResult struct {
	RunID       uuid.UUID
	OutboxIDs   []uuid.UUID
	AggregateID string
	// Replayed is true when idempotency returned an already durable result.
	// Replay is success, but is not a new commit.
	Replayed bool
}
