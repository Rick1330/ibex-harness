//go:build integration

package postgres

import (
	"database/sql"
	"strings"
	"testing"

	"github.com/lib/pq"
)

const forgeableGUCPattern = `is_service_account|current_user_id`

// A1 — no policy or function body references the old forgeable GUCs, the
// helpers stay SECURITY INVOKER, and the readers stay SECURITY DEFINER.
func TestTenancyPolicyInvariants(t *testing.T) {
	f := newTenancyFixture(t)
	f.assertNoRows(`
		SELECT schemaname || '.' || tablename || '.' || policyname
		FROM pg_policies
		WHERE coalesce(qual, '') ~ $1 OR coalesce(with_check, '') ~ $1`, forgeableGUCPattern)
	f.assertNoRows(`
		SELECT n.nspname || '.' || p.proname
		FROM pg_proc p
		JOIN pg_namespace n ON n.oid = p.pronamespace
		WHERE p.prokind = 'f' AND pg_get_functiondef(p.oid) ~ $1`, forgeableGUCPattern)

	f.assertProsecdef([]string{"rls_org_visible", "rls_evidence_visible", "rls_privacy_visible"}, false)
	f.assertProsecdef([]string{
		"auth_find_token_by_prefix", "rate_limit_overrides_snapshot", "sessions_abandon_idle",
		"budget_reservations_expire_stale", "active_periods",
	}, true)
}

func (f *tenancyFixture) assertNoRows(query, pattern string) {
	f.t.Helper()
	rows, err := f.db.QueryContext(f.ctx, query, pattern)
	if err != nil {
		f.t.Fatalf("query: %v", err)
	}
	defer rows.Close()
	if offenders := scanStrings(f.t, rows); len(offenders) > 0 {
		f.t.Fatalf("forgeable GUC still referenced by: %s", strings.Join(offenders, ", "))
	}
}

func (f *tenancyFixture) assertProsecdef(names []string, want bool) {
	f.t.Helper()
	rows, err := f.db.QueryContext(f.ctx, `
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

// A7 — the auth reader works as ibex_runtime because its owner is
// ibex_service, not because of a GUC, and ibex_app is refused.
func TestTenancyDefinerReaderUnderRuntime(t *testing.T) {
	f := newTenancyFixture(t)
	f.seedTenant()
	tokenID := f.seedToken("ibex_pat_reader", "hash-reader")

	row, err := readTokenAsRuntime(f, "ibex_pat_reader")
	if err != nil {
		t.Fatalf("reader as ibex_runtime: %v", err)
	}
	if row.tokenID != tokenID || row.orgID != f.orgID || row.status != "active" || row.hash != "hash-reader" {
		t.Fatalf("unexpected reader row: %+v", row)
	}

	err = f.withRole("ibex_app", "", func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx,
			`SELECT * FROM ibex_core.auth_find_token_by_prefix($1)`, "ibex_pat_reader")
		return err
	})
	f.requireSQLSTATE(err, "42501")
}

type tokenRow struct {
	tokenID, orgID, status, hash string
	userID, agentID              sql.NullString
	permissions                  int64
	expiresAt                    sql.NullTime
}

func readTokenAsRuntime(f *tenancyFixture, prefix string) (tokenRow, error) {
	var row tokenRow
	err := f.withRole("ibex_runtime", "", func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, `
			SELECT token_id, org_id, org_status, user_id, agent_id, permissions, expires_at, token_hash
			FROM ibex_core.auth_find_token_by_prefix($1)`, prefix,
		).Scan(&row.tokenID, &row.orgID, &row.status, &row.userID, &row.agentID,
			&row.permissions, &row.expiresAt, &row.hash)
	})
	return row, err
}

// A regression — an empty org GUC must fail closed, not raise 22P02.
func TestTenancyEmptyOrgGUCIsSafe(t *testing.T) {
	f := newTenancyFixture(t)
	var count int
	err := f.withRoleGUC("ibex_app", "", func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, `SELECT COUNT(*) FROM ibex_core.organizations`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("empty-GUC tenant read: %v", err)
	}
	if count != 0 {
		t.Fatalf("empty GUC saw %d organizations, want 0", count)
	}
}

// A regression — the definer recover function must tolerate the empty GUC on a
// pooled connection, both directly and after a real org was set and cleared.
func TestTenancyEvidenceRecoverWithEmptyGUC(t *testing.T) {
	f := newTenancyFixture(t)
	f.seedTenant()
	assertRecoverReturnsZero(t, f, "")
	assertRecoverAfterClearing(t, f)
}

func assertRecoverReturnsZero(t *testing.T, f *tenancyFixture, guc string) {
	t.Helper()
	var n int64
	err := f.withRoleGUC("ibex_service", guc, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx,
			`SELECT ibex_core.evidence_outbox_recover_in_flight(1.0)`).Scan(&n)
	})
	if err != nil {
		t.Fatalf("recover with guc=%q: %v", guc, err)
	}
	if n != 0 {
		t.Fatalf("recover with guc=%q returned %d, want 0", guc, n)
	}
}

func assertRecoverAfterClearing(t *testing.T, f *tenancyFixture) {
	t.Helper()
	var n int64
	err := f.withRoleGUC("ibex_service", f.orgID, func(tx *sql.Tx) error {
		if err := f.setOrgGUC(tx, ""); err != nil {
			return err
		}
		return tx.QueryRowContext(f.ctx,
			`SELECT ibex_core.evidence_outbox_recover_in_flight(1.0)`).Scan(&n)
	})
	if err != nil {
		t.Fatalf("recover after clearing the GUC: %v", err)
	}
	if n != 0 {
		t.Fatalf("recover after clearing returned %d, want 0", n)
	}
}
