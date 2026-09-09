//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"testing"
)

// SeedOrganization inserts a test organization and returns its ID.
func SeedOrganization(t testing.TB, db *sql.DB, name, slug string) string {
	t.Helper()
	ctx := context.Background()
	var id string
	err := WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ($1, $2)
			RETURNING id::text`, name, slug,
		).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed organization: %v", err)
	}
	return id
}

// SeedUser inserts a user for orgID and returns its user ID.
func SeedUser(t testing.TB, db *sql.DB, orgID, email, name string) string {
	t.Helper()
	ctx := context.Background()
	var id string
	err := WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.users (org_id, email, name)
			VALUES ($1::uuid, $2, $3)
			RETURNING id::text`, orgID, email, name,
		).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed user: %v", err)
	}
	return id
}

// SoftDeleteUser mirrors management-API soft-delete (status + deleted_at).
func SoftDeleteUser(t testing.TB, db *sql.DB, orgID, userID string) {
	t.Helper()
	ctx := context.Background()
	err := WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		stmt, err := tx.PrepareContext(ctx, softDeleteUserSQL)
		if err != nil {
			return err
		}
		defer stmt.Close()
		_, err = stmt.ExecContext(ctx, userID, orgID)
		return err
	})
	if err != nil {
		t.Fatalf("soft-delete user: %v", err)
	}
}

const softDeleteUserSQL = `
	UPDATE ibex_core.users
	SET status = 'deactivated', deleted_at = NOW()
	WHERE id = $1::uuid AND org_id = $2::uuid AND deleted_at IS NULL`

// SeedAgent inserts an agent for orgID, optionally referenced by created_by=userID, and returns its agent ID.
func SeedAgent(t testing.TB, db *sql.DB, orgID, userID, name, slug string) string {
	t.Helper()
	ctx := context.Background()
	var id string
	err := WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			VALUES ($1::uuid, $2::uuid, $3, $4)
			RETURNING id::text`, orgID, userID, name, slug,
		).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed agent: %v", err)
	}
	return id
}

// SeedAgentWithStatus inserts an agent with the given status (active, paused, archived, suspended).
func SeedAgentWithStatus(t testing.TB, db *sql.DB, orgID, userID, name, slug, agentStatus string) string {
	t.Helper()
	ctx := context.Background()
	var id string
	err := WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug, status)
			VALUES ($1::uuid, $2::uuid, $3, $4, $5)
			RETURNING id::text`, orgID, userID, name, slug, agentStatus,
		).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed agent with status %q: %v", agentStatus, err)
	}
	return id
}
