//go:build integration

package postgres

import (
	"bytes"
	"context"
	"database/sql"
	"fmt"
	"net"
	"net/url"
	"strings"
	"testing"
	"time"
)

const (
	runtimeSecret   = "capability-test-only"
	workerSecret    = "capability-test-only-worker"
	bootstrapSecret = "capability-test-only-bootstrap"
)

// setProvisionEnv provides the three capability secrets for a test.
func setProvisionEnv(t *testing.T) {
	t.Helper()
	t.Setenv("IBEX_RUNTIME_DB_PASSWORD", runtimeSecret)
	t.Setenv("IBEX_WORKER_DB_PASSWORD", workerSecret)
	t.Setenv("IBEX_BOOTSTRAP_DB_PASSWORD", bootstrapSecret)
}

// TestProvisionSetsScramAndAllowsLogin proves the inert-to-provisioned
// transition, the SCRAM verifier, and password authentication over TCP.
func TestProvisionSetsScramAndAllowsLogin(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	assertCapabilityConnLimits(f, ctx, 0)
	setProvisionEnv(t)
	if err := Provision(f.dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}
	assertCapabilityConnLimits(f, ctx, -1)
	assertScramVerifier(t, f, provisionCredential{
		target: provisionTarget{role: "ibex_runtime"}, password: runtimeSecret,
	})
	assertRuntimeLogin(t, f, ctx, runtimeSecret)
}

// assertCapabilityConnLimits checks all three login limits.
func assertCapabilityConnLimits(f *tenancyFixture, ctx context.Context, want int) {
	f.t.Helper()
	for _, name := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		f.assertConnLimit(ctx, connLimitCheck{spec: role(name), want: want})
	}
}

// assertScramVerifier checks the stored verifier is SCRAM and not plaintext.
func assertScramVerifier(t *testing.T, f *tenancyFixture, credential provisionCredential) {
	t.Helper()
	var stored string
	if err := f.db.QueryRowContext(t.Context(),
		`SELECT rolpassword FROM pg_authid WHERE rolname = $1`, credential.target.role).Scan(&stored); err != nil {
		t.Fatalf("read rolpassword: %v", err)
	}
	if !strings.HasPrefix(stored, "SCRAM-SHA-256$") || strings.Contains(stored, credential.password) {
		t.Fatalf("unexpected stored verifier for %s", credential.target.role)
	}
}

// assertRuntimeLogin proves the correct password works and a wrong one fails.
func assertRuntimeLogin(t *testing.T, f *tenancyFixture, ctx context.Context, secret string) {
	t.Helper()
	base, err := url.Parse(f.dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	host := net.JoinHostPort(base.Hostname(), dsnPort(base))
	conn, err := net.DialTimeout("tcp", host, 2*time.Second)
	if err != nil {
		t.Skipf("test DSN is not TCP-reachable at %s: %v", host, err)
	}
	_ = conn.Close()

	correct := runtimeConnectionURL(base, secret)
	if err := assertLogin(t, ctx, correct, "ibex_runtime"); err != nil {
		t.Fatalf("correct password rejected: %v", err)
	}
	wrong := runtimeConnectionURL(base, secret+"-wrong")
	if err := assertLogin(t, ctx, wrong, "ibex_runtime"); err == nil {
		t.Skip("server accepted a wrong password (trust auth); password-auth proof unavailable")
	}
}

// runtimeConnectionURL builds an ibex_runtime URL with the given secret.
func runtimeConnectionURL(base *url.URL, secret string) string {
	clone := *base
	clone.User = url.UserPassword("ibex_runtime", secret)
	return clone.String()
}

// assertLogin connects, pings and checks current_user; it returns the ping
// error so the caller can assert a wrong password is rejected.
func assertLogin(t *testing.T, ctx context.Context, dsn, wantUser string) error {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open connection: %v", err)
	}
	defer db.Close()
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		return err
	}
	var current string
	if err := db.QueryRowContext(ctx, `SELECT current_user`).Scan(&current); err != nil {
		t.Fatalf("select current_user: %v", err)
	}
	if current != wantUser {
		t.Fatalf("current_user = %q, want %q", current, wantUser)
	}
	assertSetRoleApp(t, ctx, db)
	return nil
}

// dsnPort returns the DSN port or PostgreSQL's default.
func dsnPort(base *url.URL) string {
	if port := base.Port(); port != "" {
		return port
	}
	return "5432"
}

// assertSetRoleApp proves the login can assume ibex_app.
func assertSetRoleApp(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		t.Fatalf("set role ibex_app: %v", err)
	}
	var current string
	if err := tx.QueryRowContext(ctx, `SELECT current_user`).Scan(&current); err != nil {
		t.Fatalf("select current_user after SET ROLE: %v", err)
	}
	if current != "ibex_app" {
		t.Fatalf("current_user after SET ROLE = %q, want ibex_app", current)
	}
}

// TestTenancyDownUpCycle proves all migrations reverse and re-apply.
func TestTenancyDownUpCycle(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	want := maxEmbeddedMigrationVersion(t)
	f.assertVersion(ctx, versionCheck{want: want})
	assertIndex(f, ctx, true)

	for i := 0; i < 5; i++ {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down %d: %v", i+1, err)
		}
	}
	f.assertVersion(ctx, versionCheck{want: want - 5})
	assertIndex(f, ctx, false)
	assertServiceBypass(f, ctx, true)
	assertCapabilityRoles(f, ctx, 0)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up: %v", err)
	}
	f.assertVersion(ctx, versionCheck{want: want})
	assertIndex(f, ctx, true)
	assertServiceBypass(f, ctx, false)
	assertCapabilityRoles(f, ctx, 4)
}

// assertIndex checks the token-prefix index exists.
func assertIndex(f *tenancyFixture, ctx context.Context, want bool) {
	f.t.Helper()
	got := f.indexExists(ctx, indexName{qualified: "ibex_core.idx_tokens_prefix"})
	if got != want {
		f.t.Fatalf("idx_tokens_prefix exists = %v, want %v", got, want)
	}
}

// assertServiceBypass checks ibex_service's BYPASSRLS attribute.
func assertServiceBypass(f *tenancyFixture, ctx context.Context, want bool) {
	f.t.Helper()
	got := f.loadRoleFlags(ctx, role("ibex_service")).bypass
	if got != want {
		f.t.Fatalf("ibex_service rolbypassrls = %v, want %v", got, want)
	}
}

// assertCapabilityRoles checks how many capability roles exist.
func assertCapabilityRoles(f *tenancyFixture, ctx context.Context, want int) {
	f.t.Helper()
	got := f.roleCount(ctx, roleSet{names: []string{"ibex_purge", "ibex_runtime", "ibex_worker", "ibex_bootstrap"}})
	if got != want {
		f.t.Fatalf("capability roles = %d, want %d", got, want)
	}
}

// TestProvisionedLoginSurvivesReRun proves a normal migration cycle keeps -1.
func TestProvisionedLoginSurvivesReRun(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	setProvisionEnv(t)
	if err := Provision(f.dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}
	f.assertConnLimit(ctx, connLimitCheck{spec: role("ibex_runtime"), want: -1})
	if err := Down(f.dsn); err != nil {
		t.Fatalf("down: %v", err)
	}
	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	f.assertConnLimit(ctx, connLimitCheck{spec: role("ibex_runtime"), want: -1})
}

// TestExistingProvisionedRoleKeepsLimit proves 000064's ELSE branch leaves the
// limit alone when the role pre-exists.
func TestExistingProvisionedRoleKeepsLimit(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for i := 0; i < 5; i++ {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down %d: %v", i+1, err)
		}
	}
	if _, err := f.db.ExecContext(ctx, `
		CREATE ROLE ibex_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
		NOBYPASSRLS NOINHERIT CONNECTION LIMIT -1`); err != nil {
		t.Fatalf("create pre-existing role: %v", err)
	}
	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	f.assertConnLimit(ctx, connLimitCheck{spec: role("ibex_runtime"), want: -1})
}

// TestMigrationRejectsProvisionedWorkerBeforeGrant proves 000064 refuses to
// grant ibex_purge to a pre-existing, already-provisioned ibex_worker.
func TestMigrationRejectsProvisionedWorkerBeforeGrant(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for i := 0; i < 5; i++ {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down %d: %v", i+1, err)
		}
	}
	f.exec(ctx, fmt.Sprintf(`
		CREATE ROLE ibex_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
		NOBYPASSRLS NOINHERIT PASSWORD '%s'`,
		scramSHA256Verifier(scramInput{
			password: runtimeSecret, salt: bytes.Repeat([]byte{1}, scramSaltBytes), iterations: scramIterations,
		})))
	err := Up(f.dsn)
	if err == nil {
		t.Fatal("expected 000064 to reject a provisioned worker")
	}
	if !strings.Contains(err.Error(), "pre-exists with a credential") {
		t.Fatalf("unexpected error: %v", err)
	}
}

// driftCase is one pre-provision drift that must make Provision reject.
type driftCase struct {
	name  string
	apply func(context.Context, *tenancyFixture)
}

// TestProvisionRejectsDrift proves late rejections roll back every change.
func TestProvisionRejectsDrift(t *testing.T) {
	for _, tc := range driftCases() {
		t.Run(tc.name, func(t *testing.T) {
			f := newTenancyFixture(t)
			ctx := t.Context()
			setProvisionEnv(t)
			tc.apply(ctx, f)
			if err := Provision(f.dsn); err == nil {
				t.Fatal("expected Provision to reject the drift")
			}
			assertRolesUnprovisioned(t, f, ctx)
		})
	}
}

// driftCases covers unsafe attributes, direct/indirect forbidden memberships,
// a missing required role, an expired credential and a bootstrap tenant drift.
func driftCases() []driftCase {
	return []driftCase{
		{"unsafe attributes", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `ALTER ROLE ibex_runtime SUPERUSER`)
		}},
		{"direct forbidden", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `GRANT ibex_service TO ibex_runtime`)
		}},
		{"indirect forbidden", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `CREATE ROLE drift_bridge NOLOGIN`)
			f.exec(ctx, `GRANT ibex_service TO drift_bridge`)
			f.exec(ctx, `GRANT drift_bridge TO ibex_runtime`)
			f.t.Cleanup(func() {
				cleanupCtx := context.Background()
				f.exec(cleanupCtx, `REVOKE drift_bridge FROM ibex_runtime`)
				f.exec(cleanupCtx, `DROP OWNED BY drift_bridge`)
				f.exec(cleanupCtx, `DROP ROLE IF EXISTS drift_bridge`)
			})
		}},
		{"missing required", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `REVOKE ibex_app FROM ibex_runtime`)
		}},
		{"expired credential", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `ALTER ROLE ibex_runtime VALID UNTIL '2000-01-01'`)
		}},
		{"bootstrap tenant drift", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `GRANT ibex_app TO ibex_bootstrap`)
		}},
	}
}

// exec runs a fixture-level statement and fails on error.
func (f *tenancyFixture) exec(ctx context.Context, query string) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx, query); err != nil {
		f.t.Fatalf("exec %q: %v", query, err)
	}
}

// assertRolesUnprovisioned proves the rollback left every role inert.
func assertRolesUnprovisioned(t *testing.T, f *tenancyFixture, ctx context.Context) {
	t.Helper()
	for _, name := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		var hasPassword bool
		if err := f.db.QueryRowContext(ctx,
			`SELECT rolpassword IS NOT NULL FROM pg_authid WHERE rolname = $1`, name).Scan(&hasPassword); err != nil {
			t.Fatalf("read password state for %s: %v", name, err)
		}
		if hasPassword {
			t.Fatalf("%s kept a password after a rejected Provision", name)
		}
		f.assertConnLimit(ctx, connLimitCheck{spec: role(name), want: 0})
	}
}
