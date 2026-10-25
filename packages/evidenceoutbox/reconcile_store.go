package evidenceoutbox

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// ReconcileRun verifies a previous ambiguous/failed PersistRun outcome using
// the durable PostgreSQL run and outbox rows under the caller's org RLS scope.
// Every outbox payload is revalidated (including its digest, redaction class,
// and fence) before a retry proof is returned.
func (s *Store) ReconcileRun(ctx context.Context, in RunInput) (ReconciliationProof, error) {
	if !validReconciliationInput(in) {
		return ReconciliationProof{}, ErrReconciliationNotProven
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return ReconciliationProof{}, fmt.Errorf("evidenceoutbox: begin reconcile: %w", err)
	}
	//nolint:errcheck // rollback is harmless after commit
	defer func() { _ = tx.Rollback() }()
	if err := setOrgRLS(ctx, tx, in.OrgID); err != nil {
		return ReconciliationProof{}, err
	}
	runID, err := findReconciliationRun(ctx, tx, in)
	if err != nil {
		return ReconciliationProof{}, err
	}
	proof := ReconciliationProof{
		OrgID: in.OrgID, AgentID: cloneUUIDPointer(in.AgentID), SessionID: cloneUUIDPointer(in.SessionID),
		RequestID: in.RequestID, TraceID: in.TraceID, RunID: runID,
	}
	if err := appendVerifiedOutboxRows(ctx, tx, in, &proof); err != nil {
		return ReconciliationProof{}, err
	}
	if !proof.Matches(in) {
		return ReconciliationProof{}, ErrReconciliationNotProven
	}
	if err := tx.Commit(); err != nil {
		return ReconciliationProof{}, fmt.Errorf("evidenceoutbox: commit reconcile lookup: %w", err)
	}
	return proof, nil
}

func validReconciliationInput(in RunInput) bool {
	return in.OrgID != uuid.Nil && in.AgentID != nil && *in.AgentID != uuid.Nil &&
		in.SessionID != nil && *in.SessionID != uuid.Nil && in.RequestID != "" && in.TraceID != ""
}

func findReconciliationRun(ctx context.Context, tx *sql.Tx, in RunInput) (uuid.UUID, error) {
	var runID uuid.UUID
	var agentRaw, sessionRaw sql.NullString
	var traceID string
	err := tx.QueryRowContext(ctx, `
SELECT id, agent_id::text, session_id::text, trace_id
FROM ibex_core.evidence_runs
WHERE org_id = $1 AND request_id = $2`, in.OrgID, in.RequestID).
		Scan(&runID, &agentRaw, &sessionRaw, &traceID)
	if errors.Is(err, sql.ErrNoRows) {
		return uuid.Nil, ErrReconciliationNotProven
	}
	if err != nil {
		return uuid.Nil, fmt.Errorf("evidenceoutbox: reconcile run lookup: %w", err)
	}
	agentID, err := parseOptionalUUID(agentRaw)
	if err != nil {
		return uuid.Nil, err
	}
	sessionID, err := parseOptionalUUID(sessionRaw)
	if err != nil {
		return uuid.Nil, err
	}
	if runID == uuid.Nil || traceID != in.TraceID || !sameUUIDPtr(agentID, in.AgentID) || !sameUUIDPtr(sessionID, in.SessionID) {
		return uuid.Nil, ErrReconciliationNotProven
	}
	return runID, nil
}

func appendVerifiedOutboxRows(ctx context.Context, tx *sql.Tx, in RunInput, proof *ReconciliationProof) error {
	rows, err := tx.QueryContext(ctx, `
SELECT id, org_id, event_id, aggregate_id, aggregate_seq, schema_version, event_type,
       payload::text, payload_digest, payload_digest_scheme, delivery_status
FROM ibex_core.evidence_outbox
WHERE org_id = $1 AND aggregate_id = $2
ORDER BY aggregate_seq`, in.OrgID, in.RequestID)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: reconcile outbox lookup: %w", err)
	}
	defer func() { _ = rows.Close() }() // Also close rows on early validation returns.
	for rows.Next() {
		row, err := scanReconciliationOutboxRow(rows)
		if err != nil {
			return err
		}
		if err := addVerifiedOutboxRow(in, proof, row); err != nil {
			return err
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("evidenceoutbox: iterate reconcile rows: %w", err)
	}
	if err := rows.Close(); err != nil {
		return fmt.Errorf("evidenceoutbox: close reconcile rows: %w", err)
	}
	return nil
}

func scanReconciliationOutboxRow(rows *sql.Rows) (OutboxRow, error) {
	var row OutboxRow
	var payload []byte
	if err := rows.Scan(&row.ID, &row.OrgID, &row.EventID, &row.AggregateID,
		&row.AggregateSeq, &row.SchemaVersion, &row.EventType, &payload,
		&row.PayloadDigest, &row.PayloadDigestScheme, &row.DeliveryStatus); err != nil {
		return OutboxRow{}, fmt.Errorf("evidenceoutbox: scan reconcile row: %w", err)
	}
	row.Payload = json.RawMessage(payload)
	return row, nil
}

func addVerifiedOutboxRow(in RunInput, proof *ReconciliationProof, row OutboxRow) error {
	if row.OrgID != in.OrgID || row.AggregateID != in.RequestID || validateOutboxRow(row) != nil {
		return ErrReconciliationNotProven
	}
	proof.OutboxIDs = append(proof.OutboxIDs, row.ID)
	switch row.DeliveryStatus {
	case "pending", "failed", "in_flight":
		proof.RetryableOutboxIDs = append(proof.RetryableOutboxIDs, row.ID)
	case "delivered":
		// Already projected; exact delivery is replay-safe success.
	case "poison":
		return ErrReconciliationNotProven
	default:
		return ErrReconciliationNotProven
	}
	return nil
}

func parseOptionalUUID(value sql.NullString) (*uuid.UUID, error) {
	if !value.Valid || value.String == "" {
		return nil, nil
	}
	parsed, err := uuid.Parse(value.String)
	if err != nil {
		return nil, fmt.Errorf("evidenceoutbox: invalid UUID in reconciliation row")
	}
	return &parsed, nil
}

func cloneUUIDPointer(value *uuid.UUID) *uuid.UUID {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}
