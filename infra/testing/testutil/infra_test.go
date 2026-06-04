//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"testing"

	"github.com/google/uuid"
)

func TestIntegrationInfraSmoke(t *testing.T) {
	dsn, cleanup := SetupPostgres(t)
	defer cleanup()

	db := OpenDB(t, dsn)
	defer db.Close()

	ctx := context.Background()
	orgA := SeedOrganization(t, db, "Org A", "org-a-"+uuid.NewString()[:8])
	orgB := SeedOrganization(t, db, "Org B", "org-b-"+uuid.NewString()[:8])

	var count int
	err := WithAppRole(ctx, db, func(tx *sql.Tx) error {
		MustSetOrgContext(t, tx, orgA)
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.organizations`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count org A: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 org for org A context, got %d", count)
	}

	err = WithAppRole(ctx, db, func(tx *sql.Tx) error {
		MustSetOrgContext(t, tx, orgB)
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.organizations`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count org B: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 org for org B context, got %d", count)
	}
}
