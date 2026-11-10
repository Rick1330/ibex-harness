//go:build integration

package testutil

import (
	"context"
	"database/sql"
)

// ResetCapabilityRoles drops the capability logins so a from-scratch migration
// recreates them. Roles and memberships are cluster-global: dropping only the
// schemas leaves a credentialed ibex_worker behind, and 000064 refuses to attach
// the modelled memberships to a role it did not create.
//
// Statements are literals so no role name is concatenated into SQL, and each
// error is ignored on purpose: DROP ROLE legitimately fails while another
// database in the cluster still holds privileges for the role.
func ResetCapabilityRoles(ctx context.Context, db *sql.DB) {
	for _, statement := range []string{
		`DROP ROLE IF EXISTS ibex_purge`,
		`DROP ROLE IF EXISTS ibex_runtime`,
		`DROP ROLE IF EXISTS ibex_worker`,
		`DROP ROLE IF EXISTS ibex_bootstrap`,
	} {
		_, _ = db.ExecContext(ctx, statement)
	}
}
