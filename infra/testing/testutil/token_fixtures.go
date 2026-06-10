//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"fmt"
	"testing"

	"github.com/google/uuid"
)

type tokenSeedOpts struct {
	orgID       string
	permissions int64
	tokenID     uuid.UUID
	name        string
	suffix      string
	revoked     bool
	expired     bool
}

func seedTokenRow(t testing.TB, db *sql.DB, opts tokenSeedOpts) string {
	t.Helper()
	tokenID := opts.tokenID
	if tokenID == uuid.Nil {
		tokenID = uuid.New()
	}
	plaintext := fmt.Sprintf("ibex_pat_%s_%s", tokenID.String(), opts.suffix)
	prefix := "ibex_pat_" + tokenID.String()
	hash, err := hashBearerForTest(plaintext)
	if err != nil {
		t.Fatalf("hash token: %v", err)
	}
	expiresClause := "NULL"
	if opts.expired {
		expiresClause = "NOW() - INTERVAL '1 hour'"
	}
	ctx := context.Background()
	query := fmt.Sprintf(`
		INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, expires_at)
		VALUES ($1::uuid, 'pat', $2, $3, $4, $5, $6, %s)`, expiresClause)
	err = WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, query, opts.orgID, hash, prefix, opts.name, opts.permissions, opts.revoked)
		return err
	})
	if err != nil {
		t.Fatalf("seed token %q: %v", opts.name, err)
	}
	return plaintext
}

// SeedToken inserts a hashed PAT for orgID and returns the plaintext bearer and token ID.
func SeedToken(t testing.TB, db *sql.DB, orgID string, permissions int64) (plaintext string, tokenID uuid.UUID) {
	t.Helper()
	tokenID = uuid.New()
	plaintext = seedTokenRow(t, db, tokenSeedOpts{
		orgID: orgID, permissions: permissions, tokenID: tokenID,
		name: "test-pat", suffix: "integrationsecret",
	})
	return plaintext, tokenID
}

// SeedTokenExpired inserts a PAT with expires_at in the past.
func SeedTokenExpired(t testing.TB, db *sql.DB, orgID string, permissions int64) string {
	t.Helper()
	return seedTokenRow(t, db, tokenSeedOpts{
		orgID: orgID, permissions: permissions, name: "expired", suffix: "expired", expired: true,
	})
}

// SeedTokenZeroPerms inserts a PAT with permissions bitmap 0.
func SeedTokenZeroPerms(t testing.TB, db *sql.DB, orgID string) string {
	t.Helper()
	plaintext, _ := SeedToken(t, db, orgID, 0)
	return plaintext
}

// SeedTokenRevoked inserts a revoked token for negative-path tests.
func SeedTokenRevoked(t testing.TB, db *sql.DB, orgID string, permissions int64) string {
	t.Helper()
	return seedTokenRow(t, db, tokenSeedOpts{
		orgID: orgID, permissions: permissions,
		name: "revoked", suffix: "revoked", revoked: true,
	})
}
