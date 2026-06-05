//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"fmt"
	"testing"

	"github.com/google/uuid"
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

// SeedToken inserts a hashed PAT for orgID and returns the plaintext bearer and token ID.
func SeedToken(t testing.TB, db *sql.DB, orgID string, permissions int64) (plaintext string, tokenID uuid.UUID) {
	t.Helper()
	tokenID = uuid.New()
	plaintext = fmt.Sprintf("ibex_pat_%s_integrationsecret", tokenID.String())
	prefix := "ibex_pat_" + tokenID.String()
	hash, err := hashBearerForTest(plaintext)
	if err != nil {
		t.Fatalf("hash token: %v", err)
	}
	ctx := context.Background()
	err = WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, expires_at)
			VALUES ($1::uuid, 'pat', $2, $3, 'test-pat', $4, false, NULL)`,
			orgID, hash, prefix, permissions,
		)
		return err
	})
	if err != nil {
		t.Fatalf("seed token: %v", err)
	}
	return plaintext, tokenID
}

// SeedTokenRevoked inserts a revoked token for negative-path tests.
func SeedTokenRevoked(t testing.TB, db *sql.DB, orgID string, tokenID uuid.UUID, permissions int64) string {
	t.Helper()
	plaintext := fmt.Sprintf("ibex_pat_%s_revoked", tokenID.String())
	prefix := "ibex_pat_" + tokenID.String()
	hash, err := hashBearerForTest(plaintext)
	if err != nil {
		t.Fatalf("hash token: %v", err)
	}
	ctx := context.Background()
	err = WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, expires_at)
			VALUES ($1::uuid, 'pat', $2, $3, 'revoked', $4, true, NULL)`,
			orgID, hash, prefix, permissions,
		)
		return err
	})
	if err != nil {
		t.Fatalf("seed revoked token: %v", err)
	}
	return plaintext
}
