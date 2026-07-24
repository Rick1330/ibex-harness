package directive

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

const resolveDirectiveQuery = `
SELECT dv.content, d.injection_mode, dv.id
FROM ibex_core.directives d
JOIN ibex_core.directive_versions dv ON dv.id = d.active_version_id
WHERE d.agent_id = $1
  AND d.org_id = $2
  AND d.is_active = true
LIMIT 1`

// PostgresStore loads directives via a read pool with RLS org context.
type PostgresStore struct {
	db *sql.DB
}

// NewPostgresStore constructs a Store backed by Postgres.
func NewPostgresStore(db *sql.DB) (*PostgresStore, error) {
	if db == nil {
		return nil, fmt.Errorf("directive: db is required")
	}
	return &PostgresStore{db: db}, nil
}

// Load returns the active directive for the agent, or empty Resolved on miss.
func (s *PostgresStore) Load(ctx context.Context, orgID, agentID uuid.UUID) (Resolved, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return Resolved{}, fmt.Errorf("directive: begin: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return Resolved{}, err
	}
	resolved, err := queryResolved(ctx, tx, orgID, agentID)
	if err != nil {
		return Resolved{}, err
	}
	if err := tx.Commit(); err != nil {
		return Resolved{}, fmt.Errorf("directive: commit: %w", err)
	}
	return resolved, nil
}

func setOrgRLS(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	_, err := tx.ExecContext(ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, orgID.String())
	if err != nil {
		return fmt.Errorf("directive: set org rls: %w", err)
	}
	return nil
}

func queryResolved(ctx context.Context, tx *sql.Tx, orgID, agentID uuid.UUID) (Resolved, error) {
	var content, mode string
	var versionID uuid.UUID
	err := tx.QueryRowContext(ctx, resolveDirectiveQuery, agentID, orgID).
		Scan(&content, &mode, &versionID)
	if errors.Is(err, sql.ErrNoRows) {
		return Resolved{}, nil
	}
	if err != nil {
		return Resolved{}, fmt.Errorf("directive: query: %w", err)
	}
	if mode == "" {
		mode = DefaultInjectionMode
	}
	return Resolved{Content: content, InjectionMode: mode, VersionID: versionID}, nil
}
