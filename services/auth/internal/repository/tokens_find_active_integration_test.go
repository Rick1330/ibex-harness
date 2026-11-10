//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
)

func findActiveCases() []findActiveCase {
	return []findActiveCase{
		{name: "happy path", wantFound: true},
		{name: "revoked excluded", revoked: true, wantFound: false},
		{name: "expired excluded", expired: true, wantFound: false},
	}
}

// TestTokensRepository_FindActiveByPrefix exercises the production lookup, which
// is now ibex_core.auth_find_token_by_prefix, so the revoked and expired cases
// assert the behaviour of the deployed definer rather than a hand-copied query.
func TestTokensRepository_FindActiveByPrefix(t *testing.T) {
	for _, tc := range findActiveCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			runFindActiveCase(t, tc)
		})
	}
}

// TestTokensRepository_FindActiveByPrefix_NewestWins proves the definer's
// `ORDER BY created_at DESC LIMIT 1` reaches the caller: two rows sharing a
// prefix resolve to the newer one.
func TestTokensRepository_FindActiveByPrefix_NewestWins(t *testing.T) {
	repo, db := setupTokensRepo(t)
	orgID := testutil.SeedOrganization(t, db, "Newest Org", "newest-"+uuid.NewString()[:8])
	prefix := "ibex_pat_" + uuid.NewString()
	olderHash := "hash-older-" + uuid.NewString()
	newerHash := "hash-newer-" + uuid.NewString()

	olderID, err := repo.InsertTestToken(context.Background(), repository.TestTokenParams{
		OrgID: orgID, Prefix: prefix, Hash: olderHash, Name: "older", Permissions: 1,
	})
	if err != nil {
		t.Fatalf("insert older token: %v", err)
	}
	newerID, err := repo.InsertTestToken(context.Background(), repository.TestTokenParams{
		OrgID: orgID, Prefix: prefix, Hash: newerHash, Name: "newer", Permissions: 2,
	})
	if err != nil {
		t.Fatalf("insert newer token: %v", err)
	}
	setTokenCreatedAt(t, db, olderID, time.Now().UTC().Add(-time.Hour))
	setTokenCreatedAt(t, db, newerID, time.Now().UTC())

	row, err := repo.FindActiveByPrefix(context.Background(), prefix)
	if err != nil {
		t.Fatalf("FindActiveByPrefix: %v", err)
	}
	if row.ID != newerID {
		t.Fatalf("token id = %s, want the newer %s", row.ID, newerID)
	}
	if row.Hash != newerHash {
		t.Fatalf("hash = %s, want %s", row.Hash, newerHash)
	}
}

// setTokenCreatedAt adjusts created_at so the duplicate-prefix ordering is
// deterministic; the repository insert API deliberately does not take it.
func setTokenCreatedAt(t *testing.T, db *sql.DB, tokenID string, at time.Time) {
	t.Helper()
	if _, err := db.Exec(`UPDATE ibex_core.tokens SET created_at = $1 WHERE id = $2::uuid`, at, tokenID); err != nil {
		t.Fatalf("set created_at: %v", err)
	}
}
