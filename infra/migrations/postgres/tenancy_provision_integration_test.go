//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"net"
	"net/url"
	"strings"
	"testing"
	"time"
)

const (
	runtimePassword   = `runtime-Pa'ss\word`
	workerPassword    = "worker-password-1"
	bootstrapPassword = "bootstrap-password-1"
)

func setProvisionEnv(t *testing.T) {
	t.Helper()
	t.Setenv("IBEX_RUNTIME_DB_PASSWORD", runtimePassword)
	t.Setenv("IBEX_WORKER_DB_PASSWORD", workerPassword)
	t.Setenv("IBEX_BOOTSTRAP_DB_PASSWORD", bootstrapPassword)
}

func TestProvisionSetsScramAndAllowsLogin(t *testing.T) {
	f := newTenancyFixture(t)
	for _, role := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		f.assertConnLimit(role, 0)
	}
	setProvisionEnv(t)
	if err := Provision(f.dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}
	for _, role := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		f.assertConnLimit(role, -1)
	}
	assertScramVerifier(t, f, "ibex_runtime", runtimePassword)
	assertRuntimeLogin(t, f, runtimePassword)
}

func assertScramVerifier(t *testing.T, f *tenancyFixture, role, password string) {
	t.Helper()
	var stored string
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT rolpassword FROM pg_authid WHERE rolname = $1`, role).Scan(&stored); err != nil {
		t.Fatalf("read rolpassword: %v", err)
	}
	if !strings.HasPrefix(stored, "SCRAM-SHA-256$") || strings.Contains(stored, password) {
		t.Fatalf("unexpected stored verifier for %s", role)
	}
}

func assertRuntimeLogin(t *testing.T, f *tenancyFixture, password string) {
	t.Helper()
	u, err := url.Parse(f.dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	host := net.JoinHostPort(u.Hostname(), dsnPort(u))
	conn, err := net.DialTimeout("tcp", host, 2*time.Second)
	if err != nil {
		t.Skipf("test DSN is not TCP-reachable at %s: %v", host, err)
	}
	_ = conn.Close()

	runtimeURL := *u
	runtimeURL.User = url.UserPassword("ibex_runtime", password)
	runtimeDB, err := sql.Open("postgres", runtimeURL.String())
	if err != nil {
		t.Fatalf("open runtime connection: %v", err)
	}
	defer runtimeDB.Close()
	pingCtx, cancel := context.WithTimeout(f.ctx, 5*time.Second)
	defer cancel()
	if err := runtimeDB.PingContext(pingCtx); err != nil {
		t.Fatalf("TCP login as ibex_runtime failed: %v", err)
	}
	var current string
	if err := runtimeDB.QueryRowContext(f.ctx, `SELECT current_user`).Scan(&current); err != nil {
		t.Fatalf("select current_user: %v", err)
	}
	if current != "ibex_runtime" {
		t.Fatalf("current_user = %q, want ibex_runtime", current)
	}
	assertSetRoleApp(t, runtimeDB, &current)
}

func dsnPort(u *url.URL) string {
	if port := u.Port(); port != "" {
		return port
	}
	return "5432"
}

func assertSetRoleApp(t *testing.T, db *sql.DB, current *string) {
	t.Helper()
	tx, err := db.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(context.Background(), `SET LOCAL ROLE ibex_app`); err != nil {
		t.Fatalf("set role ibex_app: %v", err)
	}
	if err := tx.QueryRowContext(context.Background(), `SELECT current_user`).Scan(current); err != nil {
		t.Fatalf("select current_user after SET ROLE: %v", err)
	}
	if *current != "ibex_app" {
		t.Fatalf("current_user after SET ROLE = %q, want ibex_app", *current)
	}
}

func TestTenancyDownUpCycle(t *testing.T) {
	f := newTenancyFixture(t)
	want := maxEmbeddedMigrationVersion(t)
	assertVersion(t, f.dsn, want)
	assertIndex(f, true)

	for i := 0; i < 5; i++ {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down %d: %v", i+1, err)
		}
	}
	assertVersion(t, f.dsn, want-5)
	assertIndex(f, false)
	assertServiceBypass(f, true)
	assertCapabilityRoles(f, 0)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up: %v", err)
	}
	assertVersion(t, f.dsn, want)
	assertIndex(f, true)
	assertServiceBypass(f, false)
	assertCapabilityRoles(f, 4)
}

func assertIndex(f *tenancyFixture, want bool) {
	f.t.Helper()
	if got := f.indexExists("ibex_core.idx_tokens_prefix"); got != want {
		f.t.Fatalf("idx_tokens_prefix exists = %v, want %v", got, want)
	}
}

func assertServiceBypass(f *tenancyFixture, want bool) {
	f.t.Helper()
	if got := f.roleBool("ibex_service", "rolbypassrls"); got != want {
		f.t.Fatalf("ibex_service rolbypassrls = %v, want %v", got, want)
	}
}

func assertCapabilityRoles(f *tenancyFixture, want int) {
	f.t.Helper()
	if got := f.roleCount("ibex_purge", "ibex_runtime", "ibex_worker", "ibex_bootstrap"); got != want {
		f.t.Fatalf("capability roles = %d, want %d", got, want)
	}
}

// B4 — a normal migration cycle must not disable an already-provisioned login.
func TestProvisionedLoginSurvivesReRun(t *testing.T) {
	f := newTenancyFixture(t)
	setProvisionEnv(t)
	if err := Provision(f.dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}
	f.assertConnLimit("ibex_runtime", -1)

	if err := Down(f.dsn); err != nil {
		t.Fatalf("down: %v", err)
	}
	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	f.assertConnLimit("ibex_runtime", -1)
}

// B4 (ELSE branch) — 000064 must not reset the limit when the role pre-exists
// with a provisioned `-1`.
func TestExistingProvisionedRoleKeepsLimit(t *testing.T) {
	f := newTenancyFixture(t)
	for i := 0; i < 5; i++ {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down %d: %v", i+1, err)
		}
	}
	if _, err := f.db.ExecContext(f.ctx, `
		CREATE ROLE ibex_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
		NOBYPASSRLS NOINHERIT CONNECTION LIMIT -1`); err != nil {
		t.Fatalf("create pre-existing role: %v", err)
	}
	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	f.assertConnLimit("ibex_runtime", -1)
}
