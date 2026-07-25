package session

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

// SweepAdvisoryLockKey is a stable Postgres advisory lock for multi-replica sweepers.
const SweepAdvisoryLockKey int64 = 0x4942455853575031 // "IBEXSWP1"

const (
	defaultAbandonIdleLimit = 500
	maxAbandonIdleLimit     = 5000
)

const trySweepLockSQL = `SELECT pg_try_advisory_xact_lock($1)`

const abandonIdleSQL = `
WITH victims AS (
    SELECT id
    FROM ibex_core.sessions
    WHERE status = $1
      AND deleted_at IS NULL
      AND updated_at < $2
    ORDER BY updated_at ASC
    LIMIT $3
    FOR UPDATE SKIP LOCKED
)
UPDATE ibex_core.sessions AS s
SET status = $4, completed_at = NOW()
FROM victims AS v
WHERE s.id = v.id AND s.status = $1
RETURNING s.id, s.org_id, s.agent_id, s.external_id`

// AbandonIdle marks idle active sessions as abandoned under service-account RLS.
// Uses a transaction-scoped advisory lock so concurrent proxy replicas skip the tick.
func (s *PostgresStore) AbandonIdle(ctx context.Context, p AbandonIdleParams) (AbandonIdleResult, error) {
	ctx, span := s.tracer.Start(ctx, "PostgresStore.AbandonIdle",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.table", "ibex_core.sessions"),
			attribute.String("db.operation", "UPDATE"),
		),
	)
	defer span.End()

	result, err := s.abandonIdle(ctx, p)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, err.Error())
		return AbandonIdleResult{}, err
	}
	return result, nil
}

func (s *PostgresStore) abandonIdle(ctx context.Context, p AbandonIdleParams) (AbandonIdleResult, error) {
	if err := validateAbandonIdleParams(p); err != nil {
		return AbandonIdleResult{}, err
	}
	limit := clampAbandonLimit(p.Limit)

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return AbandonIdleResult{}, fmt.Errorf("session: begin abandon idle: %w", err)
	}
	//nolint:errcheck // rollback after commit is a no-op
	defer func() { _ = tx.Rollback() }()

	return abandonIdleTx(ctx, tx, p.IdleBefore, limit)
}

func abandonIdleTx(ctx context.Context, tx *sql.Tx, idleBefore time.Time, limit int) (AbandonIdleResult, error) {
	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return AbandonIdleResult{}, err
	}
	acquired, err := trySweepXactLock(ctx, tx)
	if err != nil {
		return AbandonIdleResult{}, err
	}
	if !acquired {
		return commitSkippedSweepLock(tx)
	}

	abandoned, err := abandonIdleInTx(ctx, tx, idleBefore, limit)
	if err != nil {
		return AbandonIdleResult{}, err
	}
	if err := tx.Commit(); err != nil {
		return AbandonIdleResult{}, fmt.Errorf("session: commit abandon idle: %w", err)
	}
	return AbandonIdleResult{Abandoned: abandoned}, nil
}

func commitSkippedSweepLock(tx *sql.Tx) (AbandonIdleResult, error) {
	if err := tx.Commit(); err != nil {
		return AbandonIdleResult{}, fmt.Errorf("session: commit abandon idle skip: %w", err)
	}
	return AbandonIdleResult{SkippedLock: true}, nil
}

func validateAbandonIdleParams(p AbandonIdleParams) error {
	if p.IdleBefore.IsZero() {
		return fmt.Errorf("session: IdleBefore is required")
	}
	return nil
}

func clampAbandonLimit(limit int) int {
	if limit < 1 {
		return defaultAbandonIdleLimit
	}
	if limit > maxAbandonIdleLimit {
		return maxAbandonIdleLimit
	}
	return limit
}

func trySweepXactLock(ctx context.Context, tx *sql.Tx) (bool, error) {
	var acquired bool
	err := tx.QueryRowContext(ctx, trySweepLockSQL, SweepAdvisoryLockKey).Scan(&acquired)
	if err != nil {
		return false, fmt.Errorf("session: try sweep lock: %w", err)
	}
	return acquired, nil
}

func abandonIdleInTx(ctx context.Context, tx *sql.Tx, idleBefore time.Time, limit int) ([]AbandonedSession, error) {
	rows, err := tx.QueryContext(ctx, abandonIdleSQL,
		StatusActive, idleBefore.UTC(), limit, StatusAbandoned)
	if err != nil {
		return nil, fmt.Errorf("session: abandon idle query: %w", err)
	}
	defer rows.Close()

	out := make([]AbandonedSession, 0, limit)
	for rows.Next() {
		row, scanErr := scanAbandonedSession(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("session: abandon idle rows: %w", err)
	}
	return out, nil
}

func scanAbandonedSession(rows *sql.Rows) (AbandonedSession, error) {
	var (
		id, orgID, agentID uuid.UUID
		ext                sql.NullString
	)
	if err := rows.Scan(&id, &orgID, &agentID, &ext); err != nil {
		return AbandonedSession{}, fmt.Errorf("session: scan abandoned: %w", err)
	}
	row := AbandonedSession{SessionID: id, OrgID: orgID, AgentID: agentID}
	if ext.Valid {
		v := ext.String
		row.ExternalID = &v
	}
	return row, nil
}
