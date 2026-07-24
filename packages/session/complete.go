package session

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

const selectSessionStatusSQL = `
SELECT status FROM ibex_core.sessions
WHERE id = $1::uuid AND org_id = $2::uuid AND deleted_at IS NULL`

const completeSessionSQL = `
UPDATE ibex_core.sessions
SET status = $1, completed_at = NOW()
WHERE id = $2::uuid AND org_id = $3::uuid
  AND deleted_at IS NULL AND status <> $1`

// Complete marks a session as completed. Already-completed sessions are a no-op.
func (s *PostgresStore) Complete(ctx context.Context, sessionID, orgID uuid.UUID) error {
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
		return err
	}
	s.metrics.IncSessionComplete(result)
	return nil
}

func (s *PostgresStore) complete(ctx context.Context, sessionID, orgID uuid.UUID) (string, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return "", fmt.Errorf("session: begin complete: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return "", err
	}

	status, err := loadSessionStatus(ctx, tx, sessionID, orgID)
	if err != nil {
		return "", err
	}
	if status == StatusCompleted {
		if err := tx.Commit(); err != nil {
			return "", fmt.Errorf("session: commit complete noop: %w", err)
		}
		return ResultNoop, nil
	}

	if err := markCompleted(ctx, tx, sessionID, orgID); err != nil {
		return "", err
	}
	if err := tx.Commit(); err != nil {
		return "", fmt.Errorf("session: commit complete: %w", err)
	}
	return ResultOK, nil
}

func loadSessionStatus(ctx context.Context, tx *sql.Tx, sessionID, orgID uuid.UUID) (string, error) {
	var status string
	err := tx.QueryRowContext(ctx, selectSessionStatusSQL, sessionID, orgID).Scan(&status)
	if err == sql.ErrNoRows {
		return "", ErrNotFound
	}
	if err != nil {
		return "", fmt.Errorf("session: load status: %w", err)
	}
	return status, nil
}

func markCompleted(ctx context.Context, tx *sql.Tx, sessionID, orgID uuid.UUID) error {
	res, err := tx.ExecContext(ctx, completeSessionSQL, StatusCompleted, sessionID, orgID)
	if err != nil {
		return fmt.Errorf("session: mark completed: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("session: mark completed rows: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}
