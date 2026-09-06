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

const selectSessionStatusSQL = `
SELECT status FROM ibex_core.sessions
WHERE id = $1::uuid AND org_id = $2::uuid AND deleted_at IS NULL`

const selectSessionIDByExternalSQL = `
SELECT id FROM ibex_core.sessions
WHERE org_id = $1::uuid AND agent_id = $2::uuid
  AND external_id = $3 AND deleted_at IS NULL
LIMIT 1`

const completeSessionSQL = `
UPDATE ibex_core.sessions
SET status = $1, completed_at = NOW()
WHERE id = $2::uuid AND org_id = $3::uuid
  AND deleted_at IS NULL AND status = $4`

// Complete marks an active session as completed by row UUID.
// Already-completed and other terminal statuses return CompleteNoop.
// Missing / soft-deleted / wrong-org sessions return CompleteNotFound (nil error).
func (s *PostgresStore) Complete(ctx context.Context, sessionID, orgID uuid.UUID) (CompleteResult, error) {
	ctx, span := s.tracer.Start(ctx, "PostgresStore.Complete",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.table", "ibex_core.sessions"),
			attribute.String("db.operation", "UPDATE"),
		),
	)
	defer span.End()

	result, err := s.complete(ctx, sessionID, orgID)
	if err != nil {
		s.metrics.IncSessionComplete(ResultError)
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return 0, err
	}
	s.metrics.IncSessionComplete(result.String())
	return result, nil
}

// CompleteByExternalID resolves (org_id, agent_id, external_id) then completes.
// Returns the session row UUID on OK or Noop so callers can enqueue by id.
func (s *PostgresStore) CompleteByExternalID(
	ctx context.Context, orgID, agentID uuid.UUID, externalID string,
) (CompleteResult, uuid.UUID, error) {
	ctx, span := s.tracer.Start(ctx, "PostgresStore.CompleteByExternalID",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.table", "ibex_core.sessions"),
			attribute.String("db.operation", "UPDATE"),
		),
	)
	defer span.End()

	if externalID == "" {
		s.metrics.IncSessionComplete(CompleteNotFound.String())
		return CompleteNotFound, uuid.Nil, nil
	}

	result, sessionID, err := s.completeByExternalID(ctx, orgID, agentID, externalID)
	if err != nil {
		s.metrics.IncSessionComplete(ResultError)
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return 0, uuid.Nil, err
	}
	s.metrics.IncSessionComplete(result.String())
	return result, sessionID, nil
}

func (s *PostgresStore) complete(ctx context.Context, sessionID, orgID uuid.UUID) (CompleteResult, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("session: begin complete session_id=%s org_id=%s: %w", sessionID, orgID, err)
	}
	//nolint:errcheck // rollback after successful commit is a no-op; discard is intentional
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return 0, err
	}

	result, err := completeInTx(ctx, tx, sessionID, orgID)
	if err != nil {
		return 0, err
	}
	if err := tx.Commit(); err != nil {
		return 0, fmt.Errorf("session: commit complete session_id=%s org_id=%s: %w", sessionID, orgID, err)
	}
	return result, nil
}

func (s *PostgresStore) completeByExternalID(
	ctx context.Context, orgID, agentID uuid.UUID, externalID string,
) (CompleteResult, uuid.UUID, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, uuid.Nil, fmt.Errorf("session: begin complete_by_external org_id=%s: %w", orgID, err)
	}
	//nolint:errcheck // rollback after successful commit is a no-op; discard is intentional
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return 0, uuid.Nil, err
	}

	sessionID, err := loadSessionIDByExternal(ctx, tx, externalLookup{
		orgID: orgID, agentID: agentID, externalID: externalID,
	})
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return CompleteNotFound, uuid.Nil, nil
		}
		return 0, uuid.Nil, err
	}

	result, err := completeInTx(ctx, tx, sessionID, orgID)
	if err != nil {
		return 0, uuid.Nil, err
	}
	if err := tx.Commit(); err != nil {
		return 0, uuid.Nil, fmt.Errorf("session: commit complete_by_external org_id=%s: %w", orgID, err)
	}
	return result, sessionID, nil
}

func completeInTx(ctx context.Context, tx *sql.Tx, sessionID, orgID uuid.UUID) (CompleteResult, error) {
	status, err := loadSessionStatus(ctx, tx, sessionID, orgID)
	if err != nil {
		return mapNotFound(err)
	}
	if status != StatusActive {
		return CompleteNoop, nil
	}
	err = markCompleted(ctx, tx, sessionID, orgID)
	if err == nil {
		return CompleteOK, nil
	}
	return resolveCompleteRace(ctx, tx, sessionRef{id: sessionID, orgID: orgID}, err)
}

func mapNotFound(err error) (CompleteResult, error) {
	if errors.Is(err, ErrNotFound) {
		return CompleteNotFound, nil
	}
	return 0, err
}

type sessionRef struct {
	id    uuid.UUID
	orgID uuid.UUID
}

func resolveCompleteRace(
	ctx context.Context, tx *sql.Tx, ref sessionRef, markErr error,
) (CompleteResult, error) {
	if !errors.Is(markErr, ErrNotFound) {
		return 0, markErr
	}
	// Concurrent Complete may have won the row lock; treat terminal as noop.
	st, loadErr := loadSessionStatus(ctx, tx, ref.id, ref.orgID)
	if loadErr != nil {
		return mapNotFound(loadErr)
	}
	if st != StatusActive {
		return CompleteNoop, nil
	}
	return 0, markErr
}

type externalLookup struct {
	orgID      uuid.UUID
	agentID    uuid.UUID
	externalID string
}

func loadSessionIDByExternal(ctx context.Context, tx *sql.Tx, p externalLookup) (uuid.UUID, error) {
	var id uuid.UUID
	err := tx.QueryRowContext(ctx, selectSessionIDByExternalSQL, p.orgID, p.agentID, p.externalID).Scan(&id)
	if err == sql.ErrNoRows {
		return uuid.Nil, ErrNotFound
	}
	if err != nil {
		return uuid.Nil, fmt.Errorf("session: load by external_id org_id=%s agent_id=%s: %w", p.orgID, p.agentID, err)
	}
	return id, nil
}

func loadSessionStatus(ctx context.Context, tx *sql.Tx, sessionID, orgID uuid.UUID) (string, error) {
	var status string
	err := tx.QueryRowContext(ctx, selectSessionStatusSQL, sessionID, orgID).Scan(&status)
	if err == sql.ErrNoRows {
		return "", ErrNotFound
	}
	if err != nil {
		return "", fmt.Errorf("session: load status session_id=%s org_id=%s: %w", sessionID, orgID, err)
	}
	return status, nil
}

func markCompleted(ctx context.Context, tx *sql.Tx, sessionID, orgID uuid.UUID) error {
	res, err := tx.ExecContext(ctx, completeSessionSQL,
		StatusCompleted, sessionID, orgID, StatusActive)
	if err != nil {
		return fmt.Errorf("session: mark completed session_id=%s org_id=%s: %w", sessionID, orgID, err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("session: mark completed rows session_id=%s org_id=%s: %w", sessionID, orgID, err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}
