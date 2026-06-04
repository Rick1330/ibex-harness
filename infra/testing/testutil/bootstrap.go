//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"fmt"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/google/uuid"
)

// SeedBootstrapAdminToken inserts an admin PAT for integration bootstrap (SQL path only).
func SeedBootstrapAdminToken(t testing.TB, db *sql.DB, orgID string) (plaintext string) {
	t.Helper()
	rowID := uuid.New()
	plaintext = fmt.Sprintf("ibex_pat_%s_bootstrapadminsecret", rowID.String())
	prefix := "ibex_pat_" + rowID.String()
	hash, err := hashBearerForTest(plaintext)
	if err != nil {
		t.Fatalf("hash bootstrap token: %v", err)
	}
	ctx := context.Background()
	err = WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens (id, org_id, type, hash, prefix, name, permissions, is_revoked, expires_at)
			VALUES ($1::uuid, $2::uuid, 'pat', $3, $4, 'bootstrap-admin', $5, false, NULL)`,
			rowID.String(), orgID, hash, prefix, permissions.Admin,
		)
		return err
	})
	if err != nil {
		t.Fatalf("seed bootstrap admin: %v", err)
	}
	return plaintext
}
