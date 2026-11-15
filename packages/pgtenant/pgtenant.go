// Package pgtenant pins a Postgres transaction to exactly one organization.
//
// A store that sets app.current_org_id without also assuming the RLS-enforcing
// role is not scoped: under the owner login the policies do not apply at all,
// and under a NOINHERIT capability login the same statement leaves the read
// running as a login that holds no table grant. This package is the single
// place the correct sequence is written.
package pgtenant

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/google/uuid"
)

// PinOrg scopes tx to orgID: it assumes the ibex_app tenant role, then sets
// app.current_org_id for the remainder of the transaction.
//
// Role first, then GUC, and the order cannot be swapped. app.current_org_id is
// read by the policies attached to the tables ibex_app can reach, so the GUC
// must be set while the effective role is the one those policies apply to. The
// capability logins (ibex_runtime, ibex_worker, ibex_auth) are NOINHERIT and
// hold no table grant of their own, so a GUC set before the role leaves the
// statement executing as the login: the policies never see the selector and the
// read fails 42501.
//
// SET LOCAL, and set_config(..., is_local = true), rather than SET, because the
// *sql.DB behind a store is a pool. A session-level SET ROLE would leave
// ibex_app and the previous org installed on a connection that the next request
// borrows, which is a cross-tenant leak that outlives the request that caused
// it. Transaction-local state is discarded by the commit or rollback that ends
// tx.
//
// tx is the parameter rather than *sql.DB for that reason: SET LOCAL outside a
// transaction is a silent no-op that reports success, so a caller with no
// transaction is refused at compile time instead of failing open at runtime.
func PinOrg(ctx context.Context, tx *sql.Tx, orgID uuid.UUID) error {
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		return fmt.Errorf("pgtenant: pin role: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID.String()); err != nil {
		return fmt.Errorf("pgtenant: pin role: %w", err)
	}
	return nil
}
