package session

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/pgtenant"
	"github.com/google/uuid"
)

// setOrgRLS pins the tenant role and org selector for this transaction. The
// pin itself lives in pgtenant so there is one implementation; this keeps the
// package's own error prefix.
func setOrgRLS(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	if err := pgtenant.PinOrg(ctx, tx, orgID); err != nil {
		return fmt.Errorf("session: set org rls org_id=%s: %w", orgID, err)
	}
	return nil
}
