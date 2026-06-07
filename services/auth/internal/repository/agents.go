package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/google/uuid"
)

// AgentRecord is the minimal projection needed by the proxy for agent identity verification.
type AgentRecord struct {
	ID     string
	OrgID  string
	Status string
}

// AgentsRepository loads agents under the service-account RLS context.
type AgentsRepository struct {
	db  *sql.DB
	obs metrics.QueryObserver
}

func NewAgentsRepository(db *sql.DB, obs metrics.QueryObserver) *AgentsRepository {
	return &AgentsRepository{db: db, obs: obs}
}

func (r *AgentsRepository) GetByIDAndOrg(
	ctx context.Context,
	agentID, orgID uuid.UUID,
) (*AgentRecord, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpGetAgentByID, start)

	var out *AgentRecord
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		// Note: org_id is part of the WHERE clause to prevent cross-tenant lookups.
		row := tx.QueryRowContext(ctx, `
			SELECT id::text, org_id::text, status
			FROM ibex_core.agents
			WHERE id = $1
			  AND org_id = $2
			  AND deleted_at IS NULL
			LIMIT 1`,
			agentID, orgID,
		)

		var rec AgentRecord
		if err := row.Scan(&rec.ID, &rec.OrgID, &rec.Status); err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				// Not found means "either it doesn't exist or it belongs to a different org".
				// Caller maps both cases to PERMISSION_DENIED to avoid cross-tenant existence leakage.
				return nil
			}
			return fmt.Errorf("query agent: %w", err)
		}
		out = &rec
		return nil
	})
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (r *AgentsRepository) withServiceAccount(ctx context.Context, fn func(*sql.Tx) error) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return fmt.Errorf("set service account: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}
