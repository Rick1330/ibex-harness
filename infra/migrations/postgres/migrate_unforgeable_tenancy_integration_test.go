//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/lib/pq"
)

const forgeableGUCPattern = `is_service_account|current_user_id`

// A1 — no policy and no function body may reference the old forgeable GUCs.
func TestUnforgeableRLSNoForgeableGUCPolicies(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	assertNoRowsMatching(t, ctx, db, `
		SELECT schemaname || '.' || tablename || '.' || policyname
		FROM pg_policies
		WHERE coalesce(qual, '') ~ $1 OR coalesce(with_check, '') ~ $1`, forgeableGUCPattern)

	assertNoRowsMatching(t, ctx, db, `
		SELECT n.nspname || '.' || p.proname
		FROM pg_proc p
		JOIN pg_namespace n ON n.oid = p.pronamespace
		WHERE p.prokind = 'f' AND pg_get_functiondef(p.oid) ~ $1`, forgeableGUCPattern)

	// The helpers must stay SECURITY INVOKER: a definer helper would make
	// current_user the owner and turn all 28 helper-based policies into no-ops.
	assertProsecdef(t, ctx, db, []string{
		"rls_org_visible",
		"rls_evidence_visible",
		"rls_privacy_visible",
	}, false)

	// The five cross-tenant readers must be definers; otherwise they execute
	// as the caller and cannot read across tenants.
	assertProsecdef(t, ctx, db, []string{
		"auth_find_token_by_prefix",
		"rate_limit_overrides_snapshot",
		"sessions_abandon_idle",
		"budget_reservations_expire_stale",
		"active_periods",
	}, true)
}

// assertProsecdef checks one group of functions with one query. A missing
// function fails the test rather than passing vacuously.
func assertProsecdef(t *testing.T, ctx context.Context, db *sql.DB, names []string, want bool) {
	t.Helper()
	rows, err := db.QueryContext(ctx, `
		SELECT p.proname, p.prosecdef
		FROM pg_proc p
		JOIN pg_namespace n ON n.oid = p.pronamespace
		WHERE n.nspname IN ('ibex_core', 'ibex_billing')
		  AND p.proname::text = ANY($1)
		ORDER BY p.proname`, pq.Array(names))
	if err != nil {
		t.Fatalf("prosecdef query: %v", err)
	}
	defer rows.Close()
	found := make(map[string]bool, len(names))
	for rows.Next() {
		var (
			name       string
			isSecurity bool
		)
		if err := rows.Scan(&name, &isSecurity); err != nil {
			t.Fatalf("scan prosecdef: %v", err)
		}
		found[name] = isSecurity
		if isSecurity != want {
			t.Errorf("%s prosecdef = %v, want %v", name, isSecurity, want)
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("prosecdef rows: %v", err)
	}
	if len(found) != len(names) {
		t.Fatalf("expected %d functions, found %d: %v", len(names), len(found), found)
	}
}

func assertNoRowsMatching(t *testing.T, ctx context.Context, db *sql.DB, query, pattern string) {
	t.Helper()
	rows, err := db.QueryContext(ctx, query, pattern)
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	defer rows.Close()
	var offenders []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan: %v", err)
		}
		offenders = append(offenders, name)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows: %v", err)
	}
	if len(offenders) > 0 {
		t.Fatalf("forgeable GUC still referenced by: %s", strings.Join(offenders, ", "))
	}
}

// A2 — only the owner login may carry rolsuper or rolbypassrls.
func TestUnforgeableRLSOnlyOwnerHasBypass(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	rows, err := db.QueryContext(ctx, `
		SELECT rolname FROM pg_roles WHERE rolsuper OR rolbypassrls ORDER BY rolname`)
	if err != nil {
		t.Fatalf("pg_roles: %v", err)
	}
	defer rows.Close()
	var got []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan: %v", err)
		}
		got = append(got, name)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows: %v", err)
	}
	if len(got) != 1 || got[0] != "ibex" {
		t.Fatalf("expected only ibex to be superuser/BYPASSRLS, got %v", got)
	}
}

// A3 — recursive membership: ibex_service has exactly ibex + ibex_bootstrap,
// and ibex_purge has exactly ibex_worker.
func TestUnforgeableRLSMemberships(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	assertMembers(t, ctx, db, "ibex_service", []string{"ibex"})
	assertMembers(t, ctx, db, "ibex_purge", []string{"ibex_worker"})
}

func assertMembers(t *testing.T, ctx context.Context, db *sql.DB, role string, want []string) {
	t.Helper()
	rows, err := db.QueryContext(ctx, `
		WITH RECURSIVE membership AS (
			SELECT am.roleid, am.member
			FROM pg_auth_members am
			WHERE am.roleid = (SELECT oid FROM pg_roles WHERE rolname = $1)
			UNION
			SELECT am.roleid, am.member
			FROM pg_auth_members am
			JOIN membership m ON am.roleid = m.member
		)
		SELECT r.rolname
		FROM membership m
		JOIN pg_roles r ON r.oid = m.member
		ORDER BY r.rolname`, role)
	if err != nil {
		t.Fatalf("members of %s: %v", role, err)
	}
	defer rows.Close()
	var got []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan: %v", err)
		}
		got = append(got, name)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows: %v", err)
	}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("members of %s = %v, want %v", role, got, want)
	}
}

// A7 — the reader works under the runtime login because its owner is
// ibex_service (current_user inside the definer), not because of a GUC, and a
// role without EXECUTE is refused.
func TestUnforgeableRLSPrivilegedReaderDefiner(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	var orgID string
	if err := db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ('Reader Org', 'reader-org') RETURNING id::text`).Scan(&orgID); err != nil {
		t.Fatalf("seed org: %v", err)
	}
	var tokenID string
	if err := db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions)
		VALUES ($1::uuid, 'pat', 'hash-reader', 'ibex_pat_reader', 'reader', 0)
		RETURNING id::text`, orgID).Scan(&tokenID); err != nil {
		t.Fatalf("seed token: %v", err)
	}

	// Runtime login: no org GUC is set, so only the definer identity can
	// satisfy the policy.
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_runtime`); err != nil {
		t.Fatalf("set role: %v", err)
	}
	var (
		gotToken, gotOrg, gotStatus, gotHash string
		gotUser, gotAgent                    sql.NullString
		permissions                          int64
		expiresAt                            sql.NullTime
	)
	if err := tx.QueryRowContext(ctx, `
		SELECT token_id, org_id, org_status, user_id, agent_id, permissions, expires_at, token_hash
		FROM ibex_core.auth_find_token_by_prefix($1)`, "ibex_pat_reader",
	).Scan(&gotToken, &gotOrg, &gotStatus, &gotUser, &gotAgent, &permissions, &expiresAt, &gotHash); err != nil {
		t.Fatalf("reader as ibex_runtime: %v", err)
	}
	if gotToken != tokenID || gotOrg != orgID || gotStatus != "active" || gotHash != "hash-reader" {
		t.Fatalf("unexpected reader row: token=%s org=%s status=%s hash=%s",
			gotToken, gotOrg, gotStatus, gotHash)
	}
	if gotUser.Valid || gotAgent.Valid || expiresAt.Valid {
		t.Fatalf("expected NULL user/agent/expiry, got %+v %+v %+v", gotUser, gotAgent, expiresAt)
	}
	if err := tx.Rollback(); err != nil {
		t.Fatalf("rollback: %v", err)
	}

	// Tenant role: no EXECUTE.
	tx2, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx2.Rollback() }()
	if _, err := tx2.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		t.Fatalf("set role ibex_app: %v", err)
	}
	_, err = tx2.QueryContext(ctx,
		`SELECT * FROM ibex_core.auth_find_token_by_prefix($1)`, "ibex_pat_reader")
	requirePQCode(t, err, "42501")
}

// The purge role can touch the org_id columns its statements filter, but it
// cannot read memory content, provider credentials, token hashes, or TOTP
// secrets.
func TestUnforgeableRLSPurgeCannotReadSecrets(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	cases := []struct {
		name    string
		allowed string
		denied  string
	}{
		{
			name:    "memory content",
			allowed: `SELECT org_id FROM ibex_core.memories LIMIT 0`,
			denied:  `SELECT content FROM ibex_core.memories LIMIT 1`,
		},
		{
			name:    "provider credentials",
			allowed: `SELECT org_id FROM ibex_core.provider_credentials LIMIT 0`,
			denied:  `SELECT ciphertext FROM ibex_core.provider_credentials LIMIT 1`,
		},
		{
			name:    "token hashes",
			allowed: `SELECT org_id FROM ibex_core.tokens LIMIT 0`,
			denied:  `SELECT hash FROM ibex_core.tokens LIMIT 1`,
		},
		{
			name:    "totp secrets",
			allowed: `SELECT org_id FROM ibex_core.user_totp_secrets LIMIT 0`,
			denied:  `SELECT ciphertext FROM ibex_core.user_totp_secrets LIMIT 1`,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tx, err := db.BeginTx(ctx, nil)
			if err != nil {
				t.Fatalf("begin: %v", err)
			}
			defer func() { _ = tx.Rollback() }()
			if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_purge`); err != nil {
				t.Fatalf("set role: %v", err)
			}
			if _, err := tx.ExecContext(ctx, tc.allowed); err != nil {
				t.Fatalf("expected %q to be allowed: %v", tc.allowed, err)
			}
			_, err = tx.ExecContext(ctx, tc.denied)
			requirePQCode(t, err, "42501")
		})
	}
}

// The legal-holds trigger refuses an active hold even when the caller omits
// the saga's `cleared_at IS NOT NULL` predicate.
func TestUnforgeableRLSLegalHoldDeleteGuard(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	var orgID, userID string
	if err := db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ('Hold Org', 'hold-org') RETURNING id::text`).Scan(&orgID); err != nil {
		t.Fatalf("seed org: %v", err)
	}
	if err := db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.users (org_id, email, name)
		VALUES ($1::uuid, 'hold@example.com', 'Hold User') RETURNING id::text`, orgID).Scan(&userID); err != nil {
		t.Fatalf("seed user: %v", err)
	}
	if _, err := db.ExecContext(ctx, `
		INSERT INTO ibex_core.legal_holds (org_id, reason, set_by)
		VALUES ($1::uuid, 'litigation', $2::uuid)`, orgID, userID); err != nil {
		t.Fatalf("seed hold: %v", err)
	}

	// The owner (operator recovery path) may delete an active hold. This must
	// stay possible; the trigger deliberately constrains only ibex_purge.
	ownerTx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin owner delete: %v", err)
	}
	if _, err := ownerTx.ExecContext(ctx, `SET LOCAL ROLE ibex`); err != nil {
		t.Fatalf("set owner role: %v", err)
	}
	res, err := ownerTx.ExecContext(ctx,
		`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, orgID)
	if err != nil {
		t.Fatalf("owner active hold delete: %v", err)
	}
	if n, err := res.RowsAffected(); err != nil || n != 1 {
		t.Fatalf("owner delete affected %d rows (err=%v), want 1", n, err)
	}
	if err := ownerTx.Rollback(); err != nil {
		t.Fatalf("rollback owner delete: %v", err)
	}

	// The saga's exact predicate deletes nothing while the hold is active.
	err = withUnforgeableRole(ctx, db, "ibex_purge", orgID, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, orgID)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n != 0 {
			return fmt.Errorf("expected 0 cleared holds deleted, got %d", n)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("saga-style active hold delete: %v", err)
	}

	// A delete that forgets the predicate is refused by the trigger.
	err = withUnforgeableRole(ctx, db, "ibex_purge", orgID, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, orgID)
		return err
	})
	requirePQCode(t, err, "23514")

	// ibex_service lost DELETE on legal_holds in 000064; the broad service
	// identity is not a hold-deletion path.
	err = withUnforgeableRole(ctx, db, "ibex_service", orgID, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid`, orgID)
		return err
	})
	requirePQCode(t, err, "42501")

	if _, err := db.ExecContext(ctx,
		`UPDATE ibex_core.legal_holds SET cleared_at = NOW() WHERE org_id = $1::uuid`, orgID); err != nil {
		t.Fatalf("clear hold: %v", err)
	}

	err = withUnforgeableRole(ctx, db, "ibex_purge", orgID, func(tx *sql.Tx) error {
		res, err := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.legal_holds WHERE org_id = $1::uuid AND cleared_at IS NOT NULL`, orgID)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		if n != 1 {
			return fmt.Errorf("expected 1 cleared hold deleted, got %d", n)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("cleared hold delete: %v", err)
	}
}

// A future cutoff would let a request-path caller abandon every tenant's live
// sessions; the function rejects it with 22023.
func TestUnforgeableRLSSessionSweepRejectsFutureCutoff(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

	err := withUnforgeableRole(ctx, db, "ibex_runtime", "", func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`SELECT * FROM ibex_core.sessions_abandon_idle(NOW() + interval '1 hour', 10)`)
		return err
	})
	requirePQCode(t, err, "22023")

	if err := withUnforgeableRole(ctx, db, "ibex_runtime", "", func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`SELECT * FROM ibex_core.sessions_abandon_idle(NOW() - interval '30 minutes', 10)`)
		return err
	}); err != nil {
		t.Fatalf("past cutoff should succeed: %v", err)
	}
}

// Provision stores a SCRAM verifier and the login can authenticate with the
// plaintext over TCP, then SET ROLE ibex_app.
func TestProvisionSetsScramAndAllowsLogin(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	const (
		runtimePassword   = `runtime-Pa'ss\word`
		workerPassword    = "worker-password"
		bootstrapPassword = "bootstrap-password"
	)
	t.Setenv("POSTGRES_PASSWORD", "owner-password")
	t.Setenv("IBEX_RUNTIME_DB_PASSWORD", runtimePassword)
	t.Setenv("IBEX_WORKER_DB_PASSWORD", workerPassword)
	t.Setenv("IBEX_BOOTSTRAP_DB_PASSWORD", bootstrapPassword)

	// Inert before provisioning regardless of pg_hba.
	for _, role := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		assertConnLimit(t, db, role, 0)
	}

	if err := Provision(dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}

	// Provision clears the limit in the same statement as the verifier.
	for _, role := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		assertConnLimit(t, db, role, -1)
	}

	ctx := context.Background()
	var stored string
	if err := db.QueryRowContext(ctx,
		`SELECT rolpassword FROM pg_authid WHERE rolname = 'ibex_runtime'`).Scan(&stored); err != nil {
		t.Fatalf("read rolpassword: %v", err)
	}
	if !strings.HasPrefix(stored, "SCRAM-SHA-256$") {
		t.Fatalf("expected a SCRAM verifier, got %q", stored)
	}
	if strings.Contains(stored, runtimePassword) {
		t.Fatal("stored verifier contains the plaintext password")
	}

	u, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	if u.Host == "" {
		t.Skip("test DSN has no TCP host; skipping the login proof")
	}
	conn, err := net.DialTimeout("tcp", u.Host, 2*time.Second)
	if err != nil {
		t.Skipf("test DSN is not TCP-reachable at %s: %v", u.Host, err)
	}
	_ = conn.Close()

	runtimeURL := *u
	runtimeURL.User = url.UserPassword("ibex_runtime", runtimePassword)
	runtimeDB, err := sql.Open("postgres", runtimeURL.String())
	if err != nil {
		t.Fatalf("open runtime connection: %v", err)
	}
	defer runtimeDB.Close()

	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := runtimeDB.PingContext(pingCtx); err != nil {
		t.Fatalf("TCP login as ibex_runtime failed: %v", err)
	}
	var current string
	if err := runtimeDB.QueryRowContext(ctx, `SELECT current_user`).Scan(&current); err != nil {
		t.Fatalf("select current_user: %v", err)
	}
	if current != "ibex_runtime" {
		t.Fatalf("current_user = %q, want ibex_runtime", current)
	}

	tx, err := runtimeDB.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		t.Fatalf("set role ibex_app: %v", err)
	}
	if err := tx.QueryRowContext(ctx, `SELECT current_user`).Scan(&current); err != nil {
		t.Fatalf("select current_user after SET ROLE: %v", err)
	}
	if current != "ibex_app" {
		t.Fatalf("current_user after SET ROLE = %q, want ibex_app", current)
	}
	if err := tx.Rollback(); err != nil {
		t.Fatalf("rollback: %v", err)
	}
}

func withUnforgeableRole(ctx context.Context, db *sql.DB, role, orgID string, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE `+role); err != nil {
		return fmt.Errorf("set role %s: %w", role, err)
	}
	if orgID != "" {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID); err != nil {
			return fmt.Errorf("set org guc: %w", err)
		}
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func requirePQCode(t *testing.T, err error, code string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected SQLSTATE %s, got nil", code)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		t.Fatalf("expected *pq.Error, got %T: %v", err, err)
	}
	if string(pqErr.Code) != code {
		t.Fatalf("expected SQLSTATE %s, got %s: %v", code, pqErr.Code, err)
	}
}

// Dev rollback: all three migrations reverse and re-apply.
func TestUnforgeableRLSDownUpCycle(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	want := maxEmbeddedMigrationVersion(t)
	assertVersion(t, dsn, want)
	ctx := context.Background()
	if !indexExists(t, ctx, db, "ibex_core.idx_tokens_prefix") {
		t.Fatal("expected 000066 up to create idx_tokens_prefix")
	}

	for i := 0; i < 4; i++ {
		if err := Down(dsn); err != nil {
			t.Fatalf("down %d: %v", i+1, err)
		}
	}
	assertVersion(t, dsn, want-4)
	if indexExists(t, ctx, db, "ibex_core.idx_tokens_prefix") {
		t.Fatal("expected 000066 down to drop idx_tokens_prefix")
	}

	if !roleBypassRLS(t, ctx, db, "ibex_service") {
		t.Fatal("expected 000063 down to restore ibex_service BYPASSRLS")
	}
	if n := roleCount(t, ctx, db, "ibex_purge", "ibex_runtime", "ibex_worker", "ibex_bootstrap"); n != 0 {
		t.Fatalf("expected capability roles dropped by 000064 down, got %d", n)
	}

	if err := Up(dsn); err != nil {
		t.Fatalf("re-up: %v", err)
	}
	assertVersion(t, dsn, want)
	if !indexExists(t, ctx, db, "ibex_core.idx_tokens_prefix") {
		t.Fatal("expected re-up to recreate idx_tokens_prefix")
	}
	if roleBypassRLS(t, ctx, db, "ibex_service") {
		t.Fatal("expected 000063 up to remove ibex_service BYPASSRLS")
	}
	if n := roleCount(t, ctx, db, "ibex_purge", "ibex_runtime", "ibex_worker", "ibex_bootstrap"); n != 4 {
		t.Fatalf("expected four capability roles after re-up, got %d", n)
	}
	assertNoRowsMatching(t, ctx, db, `
		SELECT schemaname || '.' || tablename || '.' || policyname
		FROM pg_policies
		WHERE coalesce(qual, '') ~ $1 OR coalesce(with_check, '') ~ $1`, forgeableGUCPattern)
}

func assertVersion(t *testing.T, dsn string, want uint) {
	t.Helper()
	v, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatal("expected clean migration state")
	}
	if v != want {
		t.Fatalf("version = %d, want %d", v, want)
	}
}

func roleBypassRLS(t *testing.T, ctx context.Context, db *sql.DB, role string) bool {
	t.Helper()
	var bypass bool
	if err := db.QueryRowContext(ctx,
		`SELECT rolbypassrls FROM pg_roles WHERE rolname = $1`, role).Scan(&bypass); err != nil {
		t.Fatalf("pg_roles %s: %v", role, err)
	}
	return bypass
}

func roleCount(t *testing.T, ctx context.Context, db *sql.DB, roles ...string) int {
	t.Helper()
	var n int
	if err := db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM pg_roles WHERE rolname = ANY($1)`, pq.Array(roles)).Scan(&n); err != nil {
		t.Fatalf("pg_roles count: %v", err)
	}
	return n
}

func assertConnLimit(t *testing.T, db *sql.DB, role string, want int) {
	t.Helper()
	var got int
	if err := db.QueryRow(`SELECT rolconnlimit FROM pg_roles WHERE rolname = $1`, role).Scan(&got); err != nil {
		t.Fatalf("rolconnlimit %s: %v", role, err)
	}
	if got != want {
		t.Fatalf("%s rolconnlimit = %d, want %d", role, got, want)
	}
}

func indexExists(t *testing.T, ctx context.Context, db *sql.DB, qualified string) bool {
	t.Helper()
	var exists bool
	if err := db.QueryRowContext(ctx, `SELECT to_regclass($1) IS NOT NULL`, qualified).Scan(&exists); err != nil {
		t.Fatalf("to_regclass %s: %v", qualified, err)
	}
	return exists
}
