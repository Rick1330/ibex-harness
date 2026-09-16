package evidenceoutbox

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Store persists evidence rows and outbox records in a single Postgres transaction.
type Store struct {
	db *sql.DB
}

// NewStore constructs a Store. db must be non-nil.
func NewStore(db *sql.DB) (*Store, error) {
	if db == nil {
		return nil, fmt.Errorf("evidenceoutbox: db is required")
	}
	return &Store{db: db}, nil
}

// PersistRun writes the evidence graph + outbox rows atomically under org RLS.
func (s *Store) PersistRun(ctx context.Context, in RunInput) (PersistResult, error) {
	if err := validateRunInput(in); err != nil {
		return PersistResult{}, err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PersistResult{}, fmt.Errorf("evidenceoutbox: begin: %w", err)
	}
	//nolint:errcheck // rollback after commit is a no-op
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, in.OrgID); err != nil {
		return PersistResult{}, err
	}

	runID, err := insertRun(ctx, tx, in)
	if err != nil {
		return PersistResult{}, err
	}

	var seq int64
	var outboxIDs []uuid.UUID
	enqueue := func(eventType string, payload any) error {
		seq++
		id, err := enqueueOutbox(ctx, tx, in.OrgID, in.TraceID, seq, eventType, payload)
		if err != nil {
			return err
		}
		outboxIDs = append(outboxIDs, id)
		return nil
	}

	if err := enqueue(EventTypeRunCommitted, map[string]any{
		"run_id":         runID.String(),
		"request_id":     in.RequestID,
		"trace_id":       in.TraceID,
		"root_span_id":   in.RootSpanID,
		"checkpoint_id":  uuidPtrString(in.CheckpointID),
		"schema_version": SchemaVersion,
		"completeness":   defaultCompleteness(in.Completeness),
	}); err != nil {
		return PersistResult{}, err
	}

	for _, sp := range in.Spans {
		if err := insertSpan(ctx, tx, runID, in, sp); err != nil {
			return PersistResult{}, err
		}
		if err := enqueue(EventTypeSpanCommitted, map[string]any{
			"run_id":         runID.String(),
			"trace_id":       in.TraceID,
			"span_id":        sp.SpanID,
			"parent_span_id": sp.ParentSpanID,
			"operation_kind": sp.OperationKind,
			"request_id":     in.RequestID,
			"schema_version": SchemaVersion,
		}); err != nil {
			return PersistResult{}, err
		}
	}

	if in.Metrics != nil {
		if err := insertMetrics(ctx, tx, runID, in, *in.Metrics); err != nil {
			return PersistResult{}, err
		}
		if err := enqueue(EventTypeAssemblyMetrics, map[string]any{
			"run_id":     runID.String(),
			"request_id": in.RequestID,
			"trace_id":   in.TraceID,
			"metrics":    in.Metrics,
		}); err != nil {
			return PersistResult{}, err
		}
	}

	if len(in.Candidates) > 0 {
		if err := insertCandidates(ctx, tx, runID, in, in.Candidates); err != nil {
			return PersistResult{}, err
		}
		if err := enqueue(EventTypeScoreCandidates, map[string]any{
			"run_id":     runID.String(),
			"request_id": in.RequestID,
			"trace_id":   in.TraceID,
			"count":      len(in.Candidates),
		}); err != nil {
			return PersistResult{}, err
		}
	}

	if in.Directive != nil {
		if err := insertDirective(ctx, tx, runID, in, *in.Directive); err != nil {
			return PersistResult{}, err
		}
		if err := enqueue(EventTypeDirectiveSnap, map[string]any{
			"run_id":               runID.String(),
			"request_id":           in.RequestID,
			"trace_id":             in.TraceID,
			"directive_version_id": uuidPtrString(in.Directive.DirectiveVersionID),
			"content_hash":         in.Directive.ContentHash,
		}); err != nil {
			return PersistResult{}, err
		}
	}

	for _, tool := range in.Tools {
		if err := insertTool(ctx, tx, runID, in, tool); err != nil {
			return PersistResult{}, err
		}
		if err := enqueue(EventTypeToolAudit, map[string]any{
			"run_id":          runID.String(),
			"request_id":      in.RequestID,
			"trace_id":        in.TraceID,
			"tool_name":       tool.ToolName,
			"idempotency_key": tool.IdempotencyKey,
		}); err != nil {
			return PersistResult{}, err
		}
	}

	for _, se := range in.SessionEvents {
		if err := insertSessionEvent(ctx, tx, in, se); err != nil {
			return PersistResult{}, err
		}
		if err := enqueue(EventTypeSessionEvent, map[string]any{
			"session_id":      se.SessionID.String(),
			"sequence_number": se.SequenceNumber,
			"event_type":      se.EventType,
			"request_id":      in.RequestID,
			"trace_id":        in.TraceID,
			"archived_to":     se.ArchivedTo,
		}); err != nil {
			return PersistResult{}, err
		}
	}

	if err := tx.Commit(); err != nil {
		return PersistResult{}, fmt.Errorf("evidenceoutbox: commit: %w", err)
	}
	return PersistResult{RunID: runID, OutboxIDs: outboxIDs, AggregateID: in.TraceID}, nil
}

func setOrgRLS(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	_, err := tx.ExecContext(ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, orgID.String())
	if err != nil {
		return fmt.Errorf("evidenceoutbox: set org rls: %w", err)
	}
	return nil
}

func setServiceAccountRLS(ctx context.Context, tx *sql.Tx) error {
	_, err := tx.ExecContext(ctx,
		`SELECT set_config('app.is_service_account', 'true', true)`)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: set service account rls: %w", err)
	}
	return nil
}

func validateRunInput(in RunInput) error {
	if in.OrgID == uuid.Nil {
		return fmt.Errorf("evidenceoutbox: org_id is required")
	}
	if in.RequestID == "" {
		return fmt.Errorf("evidenceoutbox: request_id is required")
	}
	if in.TraceID == "" {
		return fmt.Errorf("evidenceoutbox: trace_id is required")
	}
	return nil
}

func defaultCompleteness(v string) string {
	if v == "" {
		return "partial"
	}
	return v
}

func uuidPtrString(id *uuid.UUID) string {
	if id == nil {
		return ""
	}
	return id.String()
}

func enqueueOutbox(
	ctx context.Context,
	tx *sql.Tx,
	orgID uuid.UUID,
	aggregateID string,
	seq int64,
	eventType string,
	payload any,
) (uuid.UUID, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return uuid.Nil, fmt.Errorf("evidenceoutbox: marshal payload: %w", err)
	}
	sum := sha256.Sum256(raw)
	digest := hex.EncodeToString(sum[:])
	eventID := uuid.New()
	rowID := uuid.New()
	_, err = tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_outbox (
	id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
	event_type, payload, payload_digest, delivery_status, attempts, available_at
) VALUES (
	$1, $2, $3, $4, $5, $6,
	$7, $8::jsonb, $9, $10, 0, NOW()
)`, rowID, orgID, eventID, aggregateID, seq, SchemaVersion,
		eventType, raw, digest, StatusPending)
	if err != nil {
		return uuid.Nil, fmt.Errorf("evidenceoutbox: enqueue %s: %w", eventType, err)
	}
	return rowID, nil
}

func insertRun(ctx context.Context, tx *sql.Tx, in RunInput) (uuid.UUID, error) {
	id := uuid.New()
	started := in.StartedAt
	if started.IsZero() {
		started = time.Now().UTC()
	}
	var ended any
	if !in.EndedAt.IsZero() {
		ended = in.EndedAt.UTC()
	}
	capture := in.CaptureMode
	if capture == "" {
		capture = "metadata"
	}
	sample := in.SampleDecision
	if sample == "" {
		sample = "sampled"
	}
	status := in.Status
	if status == "" {
		status = "ok"
	}
	_, err := tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_runs (
	id, org_id, agent_id, session_id, request_id, trace_id, checkpoint_id, turn_id,
	schema_version, completeness, status, error_code, capture_mode, sample_decision,
	started_at, ended_at
) VALUES (
	$1, $2, $3, $4, $5, $6, $7, $8,
	$9, $10, $11, $12, $13, $14,
	$15, $16
)`, id, in.OrgID, in.AgentID, in.SessionID, in.RequestID, in.TraceID, in.CheckpointID, in.TurnID,
		SchemaVersion, defaultCompleteness(in.Completeness), status, nullEmpty(in.ErrorCode),
		capture, sample, started.UTC(), ended)
	if err != nil {
		return uuid.Nil, fmt.Errorf("evidenceoutbox: insert run: %w", err)
	}
	return id, nil
}

func insertSpan(ctx context.Context, tx *sql.Tx, runID uuid.UUID, in RunInput, sp SpanInput) error {
	attrs, err := json.Marshal(sp.Attributes)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: marshal span attrs: %w", err)
	}
	if attrs == nil {
		attrs = []byte("{}")
	}
	started := sp.StartedAt
	if started.IsZero() {
		started = time.Now().UTC()
	}
	var ended any
	if !sp.EndedAt.IsZero() {
		ended = sp.EndedAt.UTC()
	}
	status := sp.Status
	if status == "" {
		status = "ok"
	}
	var parent any
	if sp.ParentSpanID != "" {
		parent = sp.ParentSpanID
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_spans (
	id, org_id, run_id, trace_id, span_id, parent_span_id, request_id,
	session_id, checkpoint_id, operation_kind, status, error_code, attributes,
	started_at, ended_at
) VALUES (
	$1, $2, $3, $4, $5, $6, $7,
	$8, $9, $10, $11, $12, $13::jsonb,
	$14, $15
)`, uuid.New(), in.OrgID, runID, in.TraceID, sp.SpanID, parent, in.RequestID,
		in.SessionID, in.CheckpointID, sp.OperationKind, status, nullEmpty(sp.ErrorCode), attrs,
		started.UTC(), ended)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert span: %w", err)
	}
	return nil
}

func insertMetrics(ctx context.Context, tx *sql.Tx, runID uuid.UUID, in RunInput, m AssemblyMetrics) error {
	_, err := tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_assembly_metrics (
	id, org_id, run_id, request_id, trace_id, span_id,
	budget_calculation_ms, directive_load_ms, hot_memory_retrieval_ms, cold_memory_retrieval_ms,
	ranking_ms, packing_ms, formatting_ms, total_ms, candidates_evaluated
) VALUES (
	$1, $2, $3, $4, $5, $6,
	$7, $8, $9, $10,
	$11, $12, $13, $14, $15
)`, uuid.New(), in.OrgID, runID, in.RequestID, in.TraceID, nullEmpty(in.RootSpanID),
		m.BudgetCalculationMs, m.DirectiveLoadMs, m.HotMemoryRetrievalMs, m.ColdMemoryRetrievalMs,
		m.RankingMs, m.PackingMs, m.FormattingMs, m.TotalMs, m.CandidatesEvaluated)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert metrics: %w", err)
	}
	return nil
}

func insertCandidates(ctx context.Context, tx *sql.Tx, runID uuid.UUID, in RunInput, cands []ScoreCandidate) error {
	for _, c := range cands {
		schema := c.ScoreSchema
		if schema == "" {
			schema = ScoreSchemaInterim
		}
		excl := c.Exclusion
		if excl == "" {
			excl = "included"
		}
		comps, err := json.Marshal(c.ScoreComponents)
		if err != nil {
			return fmt.Errorf("evidenceoutbox: marshal score components: %w", err)
		}
		if comps == nil {
			comps = []byte("{}")
		}
		_, err = tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_score_candidates (
	id, org_id, run_id, request_id, trace_id, memory_id,
	retrieval_rank, final_rank, delta_rank, similarity, confidence, composite_score,
	score_schema, score_components, exclusion, token_estimate, category
) VALUES (
	$1, $2, $3, $4, $5, $6,
	$7, $8, $9, $10, $11, $12,
	$13, $14::jsonb, $15, $16, $17
)`, uuid.New(), in.OrgID, runID, in.RequestID, in.TraceID, c.MemoryID,
			c.RetrievalRank, c.FinalRank, c.DeltaRank, c.Similarity, c.Confidence, c.CompositeScore,
			schema, comps, excl, c.TokenEstimate, nullEmpty(c.Category))
		if err != nil {
			return fmt.Errorf("evidenceoutbox: insert candidate: %w", err)
		}
	}
	return nil
}

func insertDirective(ctx context.Context, tx *sql.Tx, runID uuid.UUID, in RunInput, d DirectiveSnapshot) error {
	_, err := tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_directive_snapshots (
	id, org_id, run_id, request_id, trace_id, directive_version_id, content_hash, schema_version
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
		uuid.New(), in.OrgID, runID, in.RequestID, in.TraceID,
		d.DirectiveVersionID, nullEmpty(d.ContentHash), SchemaVersion)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert directive: %w", err)
	}
	return nil
}

func insertTool(ctx context.Context, tx *sql.Tx, runID uuid.UUID, in RunInput, t ToolAudit) error {
	args, err := json.Marshal(t.SanitizedArgs)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: marshal tool args: %w", err)
	}
	if args == nil {
		args = []byte("{}")
	}
	status := t.Status
	if status == "" {
		status = "ok"
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO ibex_core.evidence_tool_audits (
	id, org_id, run_id, request_id, trace_id, span_id,
	tool_name, idempotency_key, sanitized_args, status, error_code
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)`,
		uuid.New(), in.OrgID, runID, in.RequestID, in.TraceID, nullEmpty(t.SpanID),
		t.ToolName, nullEmpty(t.IdempotencyKey), args, status, nullEmpty(t.ErrorCode))
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert tool: %w", err)
	}
	return nil
}

func insertSessionEvent(ctx context.Context, tx *sql.Tx, in RunInput, se SessionEventInput) error {
	data, err := json.Marshal(se.Data)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: marshal session event: %w", err)
	}
	if data == nil {
		data = []byte("{}")
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO ibex_core.session_events (
	session_id, org_id, sequence_number, event_type, data, archived_to,
	trace_id, span_id, request_id, checkpoint_id
) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)`,
		se.SessionID, in.OrgID, se.SequenceNumber, se.EventType, data, nullEmpty(se.ArchivedTo),
		in.TraceID, nullEmpty(in.RootSpanID), in.RequestID, in.CheckpointID)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert session_event: %w", err)
	}
	return nil
}

func nullEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}
