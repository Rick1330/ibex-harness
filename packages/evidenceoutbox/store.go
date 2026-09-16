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

	w := &runWriter{ctx: ctx, tx: tx, runID: runID, in: in}
	outboxIDs, err := w.persistAll()
	if err != nil {
		return PersistResult{}, err
	}

	if err := tx.Commit(); err != nil {
		return PersistResult{}, fmt.Errorf("evidenceoutbox: commit: %w", err)
	}
	return PersistResult{RunID: runID, OutboxIDs: outboxIDs, AggregateID: in.TraceID}, nil
}

// runWriter sequences child inserts + outbox rows for one PersistRun transaction.
type runWriter struct {
	ctx      context.Context
	tx       *sql.Tx
	runID    uuid.UUID
	in       RunInput
	seq      int64
	outboxID []uuid.UUID
}

func (w *runWriter) persistAll() ([]uuid.UUID, error) {
	if err := w.enqueue(EventTypeRunCommitted, map[string]any{
		"run_id":         w.runID.String(),
		"request_id":     w.in.RequestID,
		"trace_id":       w.in.TraceID,
		"root_span_id":   w.in.RootSpanID,
		"checkpoint_id":  uuidPtrString(w.in.CheckpointID),
		"schema_version": SchemaVersion,
		"completeness":   defaultCompleteness(w.in.Completeness),
	}); err != nil {
		return nil, err
	}
	if err := w.writeSpans(); err != nil {
		return nil, err
	}
	if err := w.writeMetrics(); err != nil {
		return nil, err
	}
	if err := w.writeCandidates(); err != nil {
		return nil, err
	}
	if err := w.writeDirective(); err != nil {
		return nil, err
	}
	if err := w.writeTools(); err != nil {
		return nil, err
	}
	if err := w.writeSessionEvents(); err != nil {
		return nil, err
	}
	return w.outboxID, nil
}

func (w *runWriter) enqueue(eventType string, payload any) error {
	w.seq++
	id, err := enqueueOutbox(w.ctx, w.tx, outboxWrite{
		OrgID:       w.in.OrgID,
		AggregateID: w.in.TraceID,
		Seq:         w.seq,
		EventType:   eventType,
		Payload:     payload,
	})
	if err != nil {
		return err
	}
	w.outboxID = append(w.outboxID, id)
	return nil
}

func (w *runWriter) writeSpans() error {
	for _, sp := range w.in.Spans {
		if err := insertSpan(w, sp); err != nil {
			return err
		}
		if err := w.enqueue(EventTypeSpanCommitted, map[string]any{
			"run_id":         w.runID.String(),
			"trace_id":       w.in.TraceID,
			"span_id":        sp.SpanID,
			"parent_span_id": sp.ParentSpanID,
			"operation_kind": sp.OperationKind,
			"request_id":     w.in.RequestID,
			"schema_version": SchemaVersion,
		}); err != nil {
			return err
		}
	}
	return nil
}

func (w *runWriter) writeMetrics() error {
	if w.in.Metrics == nil {
		return nil
	}
	if err := insertMetrics(w, *w.in.Metrics); err != nil {
		return err
	}
	return w.enqueue(EventTypeAssemblyMetrics, map[string]any{
		"run_id":     w.runID.String(),
		"request_id": w.in.RequestID,
		"trace_id":   w.in.TraceID,
		"metrics":    w.in.Metrics,
	})
}

func (w *runWriter) writeCandidates() error {
	if len(w.in.Candidates) == 0 {
		return nil
	}
	if err := insertCandidates(w, w.in.Candidates); err != nil {
		return err
	}
	return w.enqueue(EventTypeScoreCandidates, map[string]any{
		"run_id":     w.runID.String(),
		"request_id": w.in.RequestID,
		"trace_id":   w.in.TraceID,
		"count":      len(w.in.Candidates),
	})
}

func (w *runWriter) writeDirective() error {
	if w.in.Directive == nil {
		return nil
	}
	if err := insertDirective(w, *w.in.Directive); err != nil {
		return err
	}
	return w.enqueue(EventTypeDirectiveSnap, map[string]any{
		"run_id":               w.runID.String(),
		"request_id":           w.in.RequestID,
		"trace_id":             w.in.TraceID,
		"directive_version_id": uuidPtrString(w.in.Directive.DirectiveVersionID),
		"content_hash":         w.in.Directive.ContentHash,
	})
}

func (w *runWriter) writeTools() error {
	for _, tool := range w.in.Tools {
		if err := insertTool(w, tool); err != nil {
			return err
		}
		if err := w.enqueue(EventTypeToolAudit, map[string]any{
			"run_id":          w.runID.String(),
			"request_id":      w.in.RequestID,
			"trace_id":        w.in.TraceID,
			"tool_name":       tool.ToolName,
			"idempotency_key": tool.IdempotencyKey,
		}); err != nil {
			return err
		}
	}
	return nil
}

func (w *runWriter) writeSessionEvents() error {
	for _, se := range w.in.SessionEvents {
		if err := insertSessionEvent(w, se); err != nil {
			return err
		}
		if err := w.enqueue(EventTypeSessionEvent, map[string]any{
			"session_id":      se.SessionID.String(),
			"sequence_number": se.SequenceNumber,
			"event_type":      se.EventType,
			"request_id":      w.in.RequestID,
			"trace_id":        w.in.TraceID,
			"archived_to":     se.ArchivedTo,
		}); err != nil {
			return err
		}
	}
	return nil
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

type outboxWrite struct {
	OrgID       uuid.UUID
	AggregateID string
	Seq         int64
	EventType   string
	Payload     any
}

func enqueueOutbox(ctx context.Context, tx *sql.Tx, w outboxWrite) (uuid.UUID, error) {
	raw, err := json.Marshal(w.Payload)
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
)`, rowID, w.OrgID, eventID, w.AggregateID, w.Seq, SchemaVersion,
		w.EventType, raw, digest, StatusPending)
	if err != nil {
		return uuid.Nil, fmt.Errorf("evidenceoutbox: enqueue %s: %w", w.EventType, err)
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

func insertSpan(w *runWriter, sp SpanInput) error {
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
	_, err = w.tx.ExecContext(w.ctx, `
INSERT INTO ibex_core.evidence_spans (
	id, org_id, run_id, trace_id, span_id, parent_span_id, request_id,
	session_id, checkpoint_id, operation_kind, status, error_code, attributes,
	started_at, ended_at
) VALUES (
	$1, $2, $3, $4, $5, $6, $7,
	$8, $9, $10, $11, $12, $13::jsonb,
	$14, $15
)`, uuid.New(), w.in.OrgID, w.runID, w.in.TraceID, sp.SpanID, parent, w.in.RequestID,
		w.in.SessionID, w.in.CheckpointID, sp.OperationKind, status, nullEmpty(sp.ErrorCode), attrs,
		started.UTC(), ended)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert span: %w", err)
	}
	return nil
}

func insertMetrics(w *runWriter, m AssemblyMetrics) error {
	_, err := w.tx.ExecContext(w.ctx, `
INSERT INTO ibex_core.evidence_assembly_metrics (
	id, org_id, run_id, request_id, trace_id, span_id,
	budget_calculation_ms, directive_load_ms, hot_memory_retrieval_ms, cold_memory_retrieval_ms,
	ranking_ms, packing_ms, formatting_ms, total_ms, candidates_evaluated
) VALUES (
	$1, $2, $3, $4, $5, $6,
	$7, $8, $9, $10,
	$11, $12, $13, $14, $15
)`, uuid.New(), w.in.OrgID, w.runID, w.in.RequestID, w.in.TraceID, nullEmpty(w.in.RootSpanID),
		m.BudgetCalculationMs, m.DirectiveLoadMs, m.HotMemoryRetrievalMs, m.ColdMemoryRetrievalMs,
		m.RankingMs, m.PackingMs, m.FormattingMs, m.TotalMs, m.CandidatesEvaluated)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert metrics: %w", err)
	}
	return nil
}

func insertCandidates(w *runWriter, cands []ScoreCandidate) error {
	for _, c := range cands {
		if err := insertOneCandidate(w, c); err != nil {
			return err
		}
	}
	return nil
}

func insertOneCandidate(w *runWriter, c ScoreCandidate) error {
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
	_, err = w.tx.ExecContext(w.ctx, `
INSERT INTO ibex_core.evidence_score_candidates (
	id, org_id, run_id, request_id, trace_id, memory_id,
	retrieval_rank, final_rank, delta_rank, similarity, confidence, composite_score,
	score_schema, score_components, exclusion, token_estimate, category
) VALUES (
	$1, $2, $3, $4, $5, $6,
	$7, $8, $9, $10, $11, $12,
	$13, $14::jsonb, $15, $16, $17
)`, uuid.New(), w.in.OrgID, w.runID, w.in.RequestID, w.in.TraceID, c.MemoryID,
		c.RetrievalRank, c.FinalRank, c.DeltaRank, c.Similarity, c.Confidence, c.CompositeScore,
		schema, comps, excl, c.TokenEstimate, nullEmpty(c.Category))
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert candidate: %w", err)
	}
	return nil
}

func insertDirective(w *runWriter, d DirectiveSnapshot) error {
	_, err := w.tx.ExecContext(w.ctx, `
INSERT INTO ibex_core.evidence_directive_snapshots (
	id, org_id, run_id, request_id, trace_id, directive_version_id, content_hash, schema_version
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
		uuid.New(), w.in.OrgID, w.runID, w.in.RequestID, w.in.TraceID,
		d.DirectiveVersionID, nullEmpty(d.ContentHash), SchemaVersion)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert directive: %w", err)
	}
	return nil
}

func insertTool(w *runWriter, t ToolAudit) error {
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
	_, err = w.tx.ExecContext(w.ctx, `
INSERT INTO ibex_core.evidence_tool_audits (
	id, org_id, run_id, request_id, trace_id, span_id,
	tool_name, idempotency_key, sanitized_args, status, error_code
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)`,
		uuid.New(), w.in.OrgID, w.runID, w.in.RequestID, w.in.TraceID, nullEmpty(t.SpanID),
		t.ToolName, nullEmpty(t.IdempotencyKey), args, status, nullEmpty(t.ErrorCode))
	if err != nil {
		return fmt.Errorf("evidenceoutbox: insert tool: %w", err)
	}
	return nil
}

func insertSessionEvent(w *runWriter, se SessionEventInput) error {
	data, err := json.Marshal(se.Data)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: marshal session event: %w", err)
	}
	if data == nil {
		data = []byte("{}")
	}
	_, err = w.tx.ExecContext(w.ctx, `
INSERT INTO ibex_core.session_events (
	session_id, org_id, sequence_number, event_type, data, archived_to,
	trace_id, span_id, request_id, checkpoint_id
) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)`,
		se.SessionID, w.in.OrgID, se.SequenceNumber, se.EventType, data, nullEmpty(se.ArchivedTo),
		w.in.TraceID, nullEmpty(w.in.RootSpanID), w.in.RequestID, w.in.CheckpointID)
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
