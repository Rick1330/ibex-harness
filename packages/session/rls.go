package session

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
)

func setOrgRLS(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	_, err := tx.ExecContext(ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, orgID.String())
	if err != nil {
		return fmt.Errorf("session: set org rls org_id=%s: %w", orgID, err)
	}
	return nil
}
