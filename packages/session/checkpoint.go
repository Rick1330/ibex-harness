package session

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const insertCheckpointSQL = `
INSERT INTO ibex_core.checkpoints (
	session_id, org_id, agent_id, turn_index, request_id,
	messages_hash, input_tokens, output_tokens, model, provider,
	completion_hash, latency_ms, provider_request_id, is_streaming, is_complete
) VALUES (
	$1::uuid, $2::uuid, $3::uuid, $4, $5,
	$6, $7, $8, $9, $10,
	$11, $12, $13, $14, $15
) RETURNING id`

const updateSessionStatsSQL = `
UPDATE ibex_core.sessions
SET turn_count = turn_count + 1,
    total_input_tokens = total_input_tokens + $1,
    total_output_tokens = total_output_tokens + $2,
    total_latency_ms = total_latency_ms + $3
WHERE id = $4::uuid AND org_id = $5::uuid AND deleted_at IS NULL`

// AppendCheckpoint inserts an immutable turn and updates session aggregates atomically.
// On success it returns the new checkpoint row id (4.P.2 Trace Inspector join key).
func (s *PostgresStore) AppendCheckpoint(ctx context.Context, p CheckpointParams) (uuid.UUID, error) {
	ctx, span := s.tracer.Start(ctx, "PostgresStore.AppendCheckpoint",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.table", "ibex_core.checkpoints"),
			attribute.String("db.operation", "INSERT"),
		),
	)
	defer span.End()

	if err := validateCheckpointStats(p); err != nil {
		s.metrics.IncSessionCheckpoint(ResultError)
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return uuid.Nil, err
	}

	id, err := s.appendCheckpoint(ctx, p)
	if err == nil {
		s.metrics.IncSessionCheckpoint(ResultOK)
		return id, nil
	}
	if errors.Is(err, ErrDuplicateTurn) {
		s.metrics.IncSessionCheckpoint(ResultDuplicate)
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return uuid.Nil, err
	}
	s.metrics.IncSessionCheckpoint(ResultError)
	span.RecordError(err)
	span.SetStatus(codes.Error, err.Error())
	return uuid.Nil, err
}

func (s *PostgresStore) appendCheckpoint(ctx context.Context, p CheckpointParams) (uuid.UUID, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return uuid.Nil, fmt.Errorf("session: begin checkpoint session_id=%s org_id=%s turn_index=%d: %w",
			p.SessionID, p.OrgID, p.TurnIndex, err)
	}
	//nolint:errcheck // rollback after successful commit is a no-op; discard is intentional
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, p.OrgID); err != nil {
		return uuid.Nil, err
	}
	id, err := insertCheckpoint(ctx, tx, p)
	if err != nil {
		return uuid.Nil, err
	}
	if err := bumpSessionStats(ctx, tx, p); err != nil {
		return uuid.Nil, err
	}
	if err := tx.Commit(); err != nil {
		return uuid.Nil, fmt.Errorf("session: commit checkpoint session_id=%s org_id=%s turn_index=%d: %w",
			p.SessionID, p.OrgID, p.TurnIndex, err)
	}
	return id, nil
}

func insertCheckpoint(ctx context.Context, tx *sql.Tx, p CheckpointParams) (uuid.UUID, error) {
	var completion any
	if p.CompletionHash != "" {
		completion = p.CompletionHash
	}
	var providerReq any
	if p.ProviderRequestID != "" {
		providerReq = p.ProviderRequestID
	}
	var id uuid.UUID
	err := tx.QueryRowContext(ctx, insertCheckpointSQL,
		p.SessionID, p.OrgID, p.AgentID, p.TurnIndex, p.RequestID,
		p.MessagesHash, p.InputTokens, p.OutputTokens, p.Model, p.Provider,
		completion, p.LatencyMs, providerReq, p.IsStreaming, p.IsComplete,
	).Scan(&id)
	if isUniqueViolation(err) {
		return uuid.Nil, ErrDuplicateTurn
	}
	if err != nil {
		return uuid.Nil, fmt.Errorf("session: insert checkpoint session_id=%s org_id=%s turn_index=%d: %w",
			p.SessionID, p.OrgID, p.TurnIndex, err)
	}
	return id, nil
}

func bumpSessionStats(ctx context.Context, tx *sql.Tx, p CheckpointParams) error {
	res, err := tx.ExecContext(ctx, updateSessionStatsSQL,
		p.InputTokens, p.OutputTokens, p.LatencyMs, p.SessionID, p.OrgID)
	if err != nil {
		return fmt.Errorf("session: update stats session_id=%s org_id=%s turn_index=%d: %w",
			p.SessionID, p.OrgID, p.TurnIndex, err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("session: update stats rows session_id=%s org_id=%s turn_index=%d: %w",
			p.SessionID, p.OrgID, p.TurnIndex, err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

func validateCheckpointStats(p CheckpointParams) error {
	if p.InputTokens < 0 {
		return invalidCheckpointStats(p)
	}
	if p.OutputTokens < 0 {
		return invalidCheckpointStats(p)
	}
	if p.LatencyMs < 0 {
		return invalidCheckpointStats(p)
	}
	return nil
}

func invalidCheckpointStats(p CheckpointParams) error {
	return fmt.Errorf("session: invalid checkpoint stats session_id=%s org_id=%s turn_index=%d: negative token or latency",
		p.SessionID, p.OrgID, p.TurnIndex)
}
