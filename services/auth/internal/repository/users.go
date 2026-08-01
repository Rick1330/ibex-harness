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

// UserRecord is the minimal projection for org-scoped user lookups.
type UserRecord struct {
	ID    string
	OrgID string
}

// UsersRepository loads users under the service-account RLS context.
type UsersRepository struct {
	db  *sql.DB
	obs metrics.QueryObserver
}

// NewUsersRepository constructs a UsersRepository.
func NewUsersRepository(db *sql.DB, obs metrics.QueryObserver) *UsersRepository {
	return &UsersRepository{db: db, obs: obs}
}

// GetByIDAndOrg returns the user when id and org_id match and the row is not soft-deleted.
// A nil record means missing-in-org or other-org; callers must not distinguish those cases to clients.
func (r *UsersRepository) GetByIDAndOrg(
	ctx context.Context,
	userID, orgID uuid.UUID,
) (*UserRecord, error) {
	start := time.Now()
	defer observeQuery(r.obs, metrics.DBOpGetUserByID, start)

	var out *UserRecord
	err := r.withServiceAccount(ctx, func(tx *sql.Tx) error {
		row := tx.QueryRowContext(ctx, `
			SELECT id::text, org_id::text
			FROM ibex_core.users
			WHERE id = $1
			  AND org_id = $2
			  AND deleted_at IS NULL
			LIMIT 1`,
			userID, orgID,
		)
		var rec UserRecord
		if err := row.Scan(&rec.ID, &rec.OrgID); err != nil {
			if errors.Is(err, sql.ErrNoRows) {
				return nil
			}
			return fmt.Errorf("query user user_id=%s org_id=%s: %w", userID, orgID, err)
		}
		out = &rec
		return nil
	})
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (r *UsersRepository) withServiceAccount(ctx context.Context, fn func(*sql.Tx) error) error {
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
