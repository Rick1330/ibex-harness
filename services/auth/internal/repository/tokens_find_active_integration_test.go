//go:build integration

package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/google/uuid"
	"github.com/lib/pq"
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

// TestTokensRepository_FindActiveByPrefix_RefusesDuplicatePrefix proves the
// invariant migration 000071 makes structural: ibex_core.idx_tokens_prefix_unique
// refuses a second row on an existing prefix, so two tenants can never share one.
//
// The refusal is asserted as SQLSTATE 23505, not as message text. Both inserts
// use distinct ids, hashes, and names, so the only index that can refuse the
// second row is the prefix index; a 23505 from another unique index would mean
// the seed itself is wrong, not that the prefix invariant holds.
//
// The reader is asserted afterwards on purpose: the index guards the writer, and
// FindActiveByPrefix runs on every authenticated request. If the refusal ever
// left the lookup unable to resolve the surviving row, authentication would break
// for the tenant that owns the prefix.
func TestTokensRepository_FindActiveByPrefix_RefusesDuplicatePrefix(t *testing.T) {
	repo, db := setupTokensRepo(t)
	ctx := context.Background()
	prefix := "ibex_pat_" + uuid.NewString()
	ownerOrg := testutil.SeedOrganization(t, db, "Prefix Owner", "prefix-owner-"+uuid.NewString()[:8])
	takerOrg := testutil.SeedOrganization(t, db, "Prefix Taker", "prefix-taker-"+uuid.NewString()[:8])

	ownerID, err := repo.InsertTestToken(ctx, repository.TestTokenParams{
		OrgID: ownerOrg, Prefix: prefix, Hash: "hash-owner-" + uuid.NewString(), Name: "owner", Permissions: 1,
	})
	if err != nil {
		t.Fatalf("insert first token: %v", err)
	}

	_, err = repo.InsertTestToken(ctx, repository.TestTokenParams{
		OrgID: takerOrg, Prefix: prefix, Hash: "hash-taker-" + uuid.NewString(), Name: "taker", Permissions: 2,
	})
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || string(pqErr.Code) != "23505" {
		t.Fatalf("second insert on prefix %s error = %v, want SQLSTATE 23505", prefix, err)
	}
	if n := countTokensWithPrefix(t, db, prefix); n != 1 {
		t.Fatalf("rows for prefix %s = %d, want 1 (the refused insert left a row behind)", prefix, n)
	}

	row, err := repo.FindActiveByPrefix(ctx, prefix)
	if err != nil {
		t.Fatalf("FindActiveByPrefix after the refused insert: %v", err)
	}
	if row.ID != ownerID {
		t.Fatalf("token id = %s, want the only surviving %s", row.ID, ownerID)
	}
	if row.OrgID != ownerOrg {
		t.Fatalf("token org = %s, want the prefix owner %s", row.OrgID, ownerOrg)
	}
	if row.Permissions != 1 {
		t.Fatalf("permissions = %d, want the surviving row's 1", row.Permissions)
	}
}

// countTokensWithPrefix counts the rows carrying prefix. It runs on the owner
// login on purpose: the invariant is global, and RLS would hide a cross-tenant
// row from a tenant-pinned connection.
func countTokensWithPrefix(t *testing.T, db *sql.DB, prefix string) int {
	t.Helper()
	var n int
	// nosemgrep: go_sql_rule-concat-sqli -- the statement is a compile-time constant and prefix is a bound parameter; no test value is ever interpolated into the SQL text.
	if err := db.QueryRow(`SELECT count(*) FROM ibex_core.tokens WHERE prefix = $1`, prefix).Scan(&n); err != nil {
		t.Fatalf("count tokens for prefix: %v", err)
	}
	return n
}
