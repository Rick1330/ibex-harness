//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/lib/pq"
)

// forgeableGUCPattern matches the two dead bypass GUCs.
const forgeableGUCPattern = `is_service_account|current_user_id`

// tokenWant is the expected token-reader row.
type tokenWant struct {
	tokenID, orgID, status, hash string
}

// gucValue is an org GUC value, including the empty string.
type gucValue struct {
	value string
}

// TestTenancyPolicyInvariants asserts A1: no policy or function body references
// the old GUCs, the helpers stay INVOKER, and the readers stay DEFINER.
func TestTenancyPolicyInvariants(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.assertNoRows(ctx, `
		SELECT schemaname || '.' || tablename || '.' || policyname
		FROM pg_policies
		WHERE coalesce(qual, '') ~ $1 OR coalesce(with_check, '') ~ $1`, forgeableGUCPattern)
	f.assertNoRows(ctx, `
		SELECT n.nspname || '.' || p.proname
		FROM pg_proc p
		JOIN pg_namespace n ON n.oid = p.pronamespace
		WHERE p.prokind = 'f' AND pg_get_functiondef(p.oid) ~ $1`, forgeableGUCPattern)
	f.assertProsecdef(ctx, []string{"rls_org_visible", "rls_evidence_visible", "rls_privacy_visible"}, false)
	f.assertProsecdef(ctx, []string{
		"auth_find_token_by_prefix", "rate_limit_overrides_snapshot", "sessions_abandon_idle",
		"budget_reservations_expire_stale", "active_periods",
		"bootstrap_upsert_organization", "bootstrap_lock_organization", "bootstrap_lookup_subjects",
		"bootstrap_create_identity", "bootstrap_insert_pat",
		"bootstrap_upsert_service_token",
	}, true)
}

// assertNoRows fails on any row returned by query with pattern bound to $1.
func (f *tenancyFixture) assertNoRows(ctx context.Context, query, pattern string) {
	f.t.Helper()
	rows, err := f.db.QueryContext(ctx, query, pattern)
	if err != nil {
		f.t.Fatalf("query: %v", err)
	}
	defer rows.Close()
	if offenders := scanStrings(f.t, rows); len(offenders) > 0 {
		f.t.Fatalf("forgeable GUC still referenced by: %s", strings.Join(offenders, ", "))
	}
}

// assertProsecdef checks one group of functions with one query.
func (f *tenancyFixture) assertProsecdef(ctx context.Context, names []string, want bool) {
	f.t.Helper()
	rows, err := f.db.QueryContext(ctx, `
		SELECT p.proname, p.prosecdef
		FROM pg_proc p
		JOIN pg_namespace n ON n.oid = p.pronamespace
		WHERE n.nspname IN ('ibex_core', 'ibex_billing')
		  AND p.proname::text = ANY($1)
		ORDER BY p.proname`, pq.Array(names))
	if err != nil {
		f.t.Fatalf("prosecdef query: %v", err)
	}
	defer rows.Close()
	found := 0
	for rows.Next() {
		var name string
		var isDefiner bool
		if err := rows.Scan(&name, &isDefiner); err != nil {
			f.t.Fatalf("scan prosecdef: %v", err)
		}
		found++
		if isDefiner != want {
			f.t.Errorf("%s prosecdef = %v, want %v", name, isDefiner, want)
		}
	}
	if err := rows.Err(); err != nil {
		f.t.Fatalf("prosecdef rows: %v", err)
	}
	if found != len(names) {
		f.t.Fatalf("expected %d functions, found %d", len(names), found)
	}
}

// TestTenancyDefinerReaderUnderAuth asserts A7: the reader works as ibex_auth
// because its owner is ibex_service, and ibex_app and ibex_runtime are refused
// (the grant moved off the runtime login in 000068).
func TestTenancyDefinerReaderUnderAuth(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.seedTenant(ctx)
	tokenID := f.seedToken(ctx, tokenSeed{prefix: "ibex_pat_reader", hash: "hash-reader"})

	row, err := readTokenAsAuth(ctx, f, "ibex_pat_reader")
	if err != nil {
		t.Fatalf("reader as ibex_auth: %v", err)
	}
	assertTokenRow(t, row, tokenWant{tokenID: tokenID, orgID: f.orgID, status: "active", hash: "hash-reader"})

	assertDefinerRefused(t, f, ctx, role("ibex_app"))
	assertDefinerRefused(t, f, ctx, role("ibex_runtime"))
}

// assertDefinerRefused asserts a role without EXECUTE is rejected with 42501.
func assertDefinerRefused(t *testing.T, f *tenancyFixture, ctx context.Context, spec roleSpec) {
	t.Helper()
	err := f.withRole(ctx, spec, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`SELECT * FROM ibex_core.auth_find_token_by_prefix($1)`, "ibex_pat_reader")
		return err
	})
	f.requireSQLSTATE(err, sqlState{code: "42501"})
}

// tokenFilter is the row shape the definer filter tests seed.
type tokenFilter struct {
	orgID     string
	prefix    string
	hash      string
	revoked   bool
	expired   bool
	createdAt time.Time
}

// TestTenancyDefinerTokenFilters proves auth_find_token_by_prefix enforces the
// same filters the deleted SQL did: revoked and expired rows and rows of a
// soft-deleted organization are excluded, and a duplicate prefix cannot be
// written at all (a unique index on tokens.prefix, 000071).
func TestTenancyDefinerTokenFilters(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.seedTenant(ctx)

	t.Run("active row is visible", func(t *testing.T) {
		id := f.seedFilterToken(ctx, tokenFilter{
			orgID: f.orgID, prefix: "filter-active", hash: "hash-active", createdAt: time.Now().UTC(),
		})
		row, err := readTokenAsAuth(ctx, f, "filter-active")
		if err != nil {
			t.Fatalf("active token: %v", err)
		}
		assertTokenRow(t, row, tokenWant{tokenID: id, orgID: f.orgID, status: "active", hash: "hash-active"})
	})

	t.Run("revoked row excluded", func(t *testing.T) {
		f.seedFilterToken(ctx, tokenFilter{
			orgID: f.orgID, prefix: "filter-revoked", hash: "hash-revoked", revoked: true, createdAt: time.Now().UTC(),
		})
		assertDefinerMiss(t, f, ctx, "filter-revoked")
	})

	t.Run("expired row excluded", func(t *testing.T) {
		f.seedFilterToken(ctx, tokenFilter{
			orgID: f.orgID, prefix: "filter-expired", hash: "hash-expired", expired: true, createdAt: time.Now().UTC(),
		})
		assertDefinerMiss(t, f, ctx, "filter-expired")
	})

	t.Run("soft-deleted organization excluded", func(t *testing.T) {
		deleted := f.seedTenantNamed(ctx, "deleted-org")
		if _, err := f.db.ExecContext(ctx,
			`UPDATE ibex_core.organizations SET deleted_at = NOW() WHERE id = $1::uuid`, deleted.orgID); err != nil {
			t.Fatalf("soft-delete org: %v", err)
		}
		f.seedFilterToken(ctx, tokenFilter{
			orgID: deleted.orgID, prefix: "filter-deleted", hash: "hash-deleted", createdAt: time.Now().UTC(),
		})
		assertDefinerMiss(t, f, ctx, "filter-deleted")
	})

	t.Run("duplicate prefix refused", func(t *testing.T) {
		f := f.sub(t)
		// 000071 makes tokens.prefix unique. The reader used to resolve two
		// rows sharing a prefix by "newest wins"; that state is now impossible,
		// so the invariant is asserted where it lives — at the write.
		f.seedFilterToken(ctx, tokenFilter{
			orgID: f.orgID, prefix: "filter-duplicate", hash: "hash-first", createdAt: time.Now().UTC(),
		})
		_, err := f.insertFilterToken(ctx, tokenFilter{
			orgID: f.orgID, prefix: "filter-duplicate", hash: "hash-second", createdAt: time.Now().UTC(),
		})
		f.requireSQLSTATE(err, sqlState{code: "23505"})
	})
}

// insertFilterToken inserts one token directly and returns its error, for the
// cases that must observe the failure.
func (f *tenancyFixture) insertFilterToken(ctx context.Context, filter tokenFilter) (string, error) {
	var expiresAt any
	if filter.expired {
		expiresAt = time.Now().UTC().Add(-time.Hour)
	}
	var id string
	err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions, is_revoked, expires_at, created_at)
		VALUES ($1::uuid, 'pat', $2, $3, 'filter', 0, $4, $5, $6)
		RETURNING id::text`,
		filter.orgID, filter.hash, filter.prefix, filter.revoked, expiresAt, filter.createdAt,
	).Scan(&id)
	return id, err
}

// seedFilterToken inserts one token directly so each filter can be set.
func (f *tenancyFixture) seedFilterToken(ctx context.Context, filter tokenFilter) string {
	f.t.Helper()
	id, err := f.insertFilterToken(ctx, filter)
	if err != nil {
		f.t.Fatalf("seed filter token %s: %v", filter.prefix, err)
	}
	return id
}

// assertDefinerMiss asserts the reader returns zero rows for a filtered prefix.
func assertDefinerMiss(t *testing.T, f *tenancyFixture, ctx context.Context, prefix string) {
	t.Helper()
	_, err := readTokenAsAuth(ctx, f, prefix)
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("%s: err = %v, want sql.ErrNoRows", prefix, err)
	}
}

// tokenRow is the eight-column auth reader result.
type tokenRow struct {
	tokenID, orgID, status, hash string
	userID, agentID              sql.NullString
	permissions                  int64
	expiresAt                    sql.NullTime
}

// readTokenAsAuth calls the auth reader as ibex_auth with no org GUC.
func readTokenAsAuth(ctx context.Context, f *tenancyFixture, prefix string) (tokenRow, error) {
	var row tokenRow
	err := f.withRole(ctx, role("ibex_auth"), func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT token_id, org_id, org_status, user_id, agent_id, permissions, expires_at, token_hash
			FROM ibex_core.auth_find_token_by_prefix($1)`, prefix,
		).Scan(&row.tokenID, &row.orgID, &row.status, &row.userID, &row.agentID,
			&row.permissions, &row.expiresAt, &row.hash)
	})
	return row, err
}

// assertTokenRow checks each auth-reader field without a compound condition.
func assertTokenRow(t *testing.T, got tokenRow, want tokenWant) {
	t.Helper()
	if got.tokenID != want.tokenID {
		t.Fatalf("token_id = %s, want %s", got.tokenID, want.tokenID)
	}
	if got.orgID != want.orgID {
		t.Fatalf("org_id = %s, want %s", got.orgID, want.orgID)
	}
	if got.status != want.status {
		t.Fatalf("status = %s, want %s", got.status, want.status)
	}
	if got.hash != want.hash {
		t.Fatalf("hash = %s, want %s", got.hash, want.hash)
	}
}

// TestTenancyEmptyOrgGUCIsSafe asserts an empty selector fails closed, not 22P02.
func TestTenancyEmptyOrgGUCIsSafe(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.seedTenant(ctx)
	var count int
	err := f.withRole(ctx, role("ibex_app").withGUC(""), func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.organizations`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("empty-GUC tenant read: %v", err)
	}
	if count != 0 {
		t.Fatalf("empty GUC saw %d organizations, want 0", count)
	}
}

// TestTenancyEvidenceRecoverWithEmptyGUC asserts the definer recover function
// tolerates the empty GUC directly and after a real org was set and cleared.
func TestTenancyEvidenceRecoverWithEmptyGUC(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.seedTenant(ctx)
	assertRecoverReturnsZero(t, f, ctx, gucValue{value: ""})
	assertRecoverAfterClearing(t, f, ctx)
}

// assertRecoverReturnsZero calls the recover helper with the given GUC.
func assertRecoverReturnsZero(t *testing.T, f *tenancyFixture, ctx context.Context, guc gucValue) {
	t.Helper()
	var n int64
	err := f.withRole(ctx, role("ibex_service").withGUC(guc.value), func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx,
			`SELECT ibex_core.evidence_outbox_recover_in_flight(1.0)`).Scan(&n)
	})
	if err != nil {
		t.Fatalf("recover with guc=%q: %v", guc.value, err)
	}
	if n != 0 {
		t.Fatalf("recover with guc=%q returned %d, want 0", guc.value, n)
	}
}

// assertRecoverAfterClearing sets a real org then clears it in the same tx.
func assertRecoverAfterClearing(t *testing.T, f *tenancyFixture, ctx context.Context) {
	t.Helper()
	var n int64
	err := f.withRole(ctx, role("ibex_service").withGUC(f.orgID), func(tx *sql.Tx) error {
		empty := ""
		if err := f.setOrgGUC(ctx, tx, &empty); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx,
			`SELECT ibex_core.evidence_outbox_recover_in_flight(1.0)`).Scan(&n)
	})
	if err != nil {
		t.Fatalf("recover after clearing the GUC: %v", err)
	}
	if n != 0 {
		t.Fatalf("recover after clearing returned %d, want 0", n)
	}
}
