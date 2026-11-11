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

	"github.com/Rick1330/ibex-harness/infra/testing/testcreds"
)

// TestProvisionSetsScramAndAllowsLogin proves the inert-to-provisioned
// transition, the SCRAM verifier, and password authentication over TCP.
// downErrFormat is the shared failure format for the down/up cycle.
const downErrFormat = "down %d: %v"

func TestProvisionSetsScramAndAllowsLogin(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	assertCapabilityConnLimits(f, ctx, 0)
	testcreds.SetProvisionEnv(t)
	if err := Provision(f.dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}
	assertCapabilityConnLimits(f, ctx, -1)
	assertScramVerifier(t, f, provisionCredential{
		target: provisionTarget{role: "ibex_runtime"}, password: testcreds.RuntimeLoginTestPassword,
	})
	assertRuntimeLogin(t, f, ctx, testcreds.RuntimeLoginTestPassword)
}

// assertCapabilityConnLimits checks all four login limits.
func assertCapabilityConnLimits(f *tenancyFixture, ctx context.Context, want int) {
	f.t.Helper()
	for _, name := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_auth"} {
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
	assertUniquePrefixIndex(f, ctx, true)

	rewindToPreServiceModel(t, f)
	assertIndex(f, ctx, false)
	assertUniquePrefixIndex(f, ctx, false)
	assertServiceBypass(f, ctx, true)
	assertCapabilityRoles(f, ctx, 0)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up: %v", err)
	}
	f.assertVersion(ctx, versionCheck{want: want})
	assertIndex(f, ctx, true)
	assertUniquePrefixIndex(f, ctx, true)
	assertServiceBypass(f, ctx, false)
	assertCapabilityRoles(f, ctx, 5)
}

// preServiceModelVersion is the last migration before the service-role wave:
// 000063-000069 create the capability roles, the privileged readers and the
// bootstrap definers. The reversal and foreign-role tests have to land below
// 000064 so the migration under test actually re-runs.
const preServiceModelVersion = 62

// rewindToPreServiceModel rolls the suite back to preServiceModelVersion.
// The step count is derived from the embedded set so a new migration in the
// wave cannot silently leave 000064 applied underneath a test that expects to
// re-run it.
func rewindToPreServiceModel(t *testing.T, f *tenancyFixture) {
	t.Helper()
	for version := maxEmbeddedMigrationVersion(t); version > preServiceModelVersion; version-- {
		if err := Down(f.dsn); err != nil {
			t.Fatalf(downErrFormat, version, err)
		}
	}
	f.assertVersion(t.Context(), versionCheck{want: preServiceModelVersion})
}

// assertIndex checks the token-prefix index exists.
func assertIndex(f *tenancyFixture, ctx context.Context, want bool) {
	f.t.Helper()
	got := f.indexExists(ctx, indexName{qualified: "ibex_core.idx_tokens_prefix"})
	if got != want {
		f.t.Fatalf("idx_tokens_prefix exists = %v, want %v", got, want)
	}
}

// assertUniquePrefixIndex checks the unique prefix index (000071) exists, is
// valid, and is unique. The down/up cycle is the only place both directions of
// that migration are exercised.
func assertUniquePrefixIndex(f *tenancyFixture, ctx context.Context, want bool) {
	f.t.Helper()
	if !f.indexExists(ctx, indexName{qualified: "ibex_core.idx_tokens_prefix_unique"}) {
		if want {
			f.t.Fatal("idx_tokens_prefix_unique is missing")
		}
		return
	}
	if !want {
		f.t.Fatal("idx_tokens_prefix_unique survived the rollback")
	}
	var valid, unique bool
	if err := f.db.QueryRowContext(ctx, `
		SELECT i.indisvalid, i.indisunique FROM pg_index i
		WHERE i.indexrelid = to_regclass('ibex_core.idx_tokens_prefix_unique')`).Scan(&valid, &unique); err != nil {
		f.t.Fatalf("read idx_tokens_prefix_unique flags: %v", err)
	}
	if !valid || !unique {
		f.t.Fatalf("idx_tokens_prefix_unique valid=%v unique=%v, want both", valid, unique)
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
	got := f.roleCount(ctx, roleSet{names: []string{"ibex_purge", "ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_auth"}})
	if got != want {
		f.t.Fatalf("capability roles = %d, want %d", got, want)
	}
}

// TestProvisionedLoginSurvivesReRun proves a normal migration cycle keeps -1.
func TestProvisionedLoginSurvivesReRun(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	testcreds.SetProvisionEnv(t)
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

// TestMigrationRerunsOnProvisionedCluster is the regression lock for the
// cluster-global role model. Roles, their credentials and their memberships are
// shared by every database in a cluster, so a second database resets only its
// own schemas and then re-runs 000064 against a login that `migrate provision`
// already secured. `provision` requires both ibex_app and ibex_purge to be
// reachable from ibex_worker by any membership path and never issues a GRANT, so
// it is weaker than the guard below it. 000064 is deliberately stricter: it
// demands the direct, SET-enabled rows that the migration itself creates, and
// those two rows — not the bare presence of a credential — are the provenance
// signal, so the re-run must succeed without widening anything.
func TestMigrationRerunsOnProvisionedCluster(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	testcreds.SetProvisionEnv(t)
	if err := Provision(f.dsn); err != nil {
		t.Fatalf("Provision: %v", err)
	}
	f.assertConnLimit(ctx, connLimitCheck{spec: role("ibex_worker"), want: -1})
	resetPerDatabaseState(ctx, f)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up on a provisioned cluster: %v", err)
	}
	assertWorkerPurgeMembership(ctx, f)
	// The capability ALTER ROLE deliberately omits CONNECTION LIMIT, so the
	// provisioned -1 has to survive the re-run rather than reverting to 0.
	f.assertConnLimit(ctx, connLimitCheck{spec: role("ibex_worker"), want: -1})
}

// resetPerDatabaseState drops only per-database state: the two schemas and
// golang-migrate's bookkeeping table. Cluster-global roles, credentials and
// memberships survive, which is exactly what a second database in a
// provisioned cluster sees when it migrates from scratch.
func resetPerDatabaseState(ctx context.Context, f *tenancyFixture) {
	f.t.Helper()
	f.exec(ctx, `DROP SCHEMA IF EXISTS ibex_billing CASCADE`)
	f.exec(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	f.exec(ctx, `DROP TABLE IF EXISTS schema_migrations`)
}

// assertWorkerPurgeMembership proves ibex_worker still reaches ibex_purge.
func assertWorkerPurgeMembership(ctx context.Context, f *tenancyFixture) {
	f.t.Helper()
	var isMember bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT pg_has_role('ibex_worker'::name, 'ibex_purge'::name, 'MEMBER')`).Scan(&isMember); err != nil {
		f.t.Fatalf("pg_has_role: %v", err)
	}
	if !isMember {
		f.t.Fatal("ibex_worker is not a member of ibex_purge after the re-run")
	}
}

// TestExistingProvisionedRoleKeepsLimit proves 000064's ELSE branch leaves the
// limit alone when the role pre-exists.
func TestExistingProvisionedRoleKeepsLimit(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	rewindToPreServiceModel(t, f)
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

// TestMigrationRejectsProvisionedWorkerBeforeGrant proves 000064 still refuses a
// foreign login: ibex_worker exists with a credential but reaches neither
// ibex_app nor ibex_purge, so `migrate provision` — which requires both roles
// reachable — cannot have committed it, and 000064 is stricter still. This pins
// the direct, SET-enabled condition, not bare credential presence — a
// credential on a role that holds both direct memberships is the provisioned
// case locked by TestMigrationRerunsOnProvisionedCluster.
func TestMigrationRejectsProvisionedWorkerBeforeGrant(t *testing.T) {
	assertMigrationRejectsForeignWorker(t, foreignWorkerCase{
		setup: func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, createdWorker(testcreds.RuntimeLoginTestPassword, 1))
		},
		drops: []string{`DROP ROLE IF EXISTS ibex_worker`},
	})
}

// foreignWorkerCase is one hand-built ibex_worker shape the migration must
// refuse. setup creates the roles and memberships; revokes and drops undo them
// afterwards, on the success and failure paths alike.
type foreignWorkerCase struct {
	setup   func(context.Context, *tenancyFixture)
	revokes []string
	drops   []string
}

// workerTeardown removes every membership and privilege the cases add to
// ibex_worker before the role is dropped. Every statement tolerates a missing
// object: the revokes and DROP OWNED BY raise when a role does not exist and
// dropClusterRoles discards that error, and the drops are IF EXISTS. The same
// teardown therefore serves every case, including one whose setup failed
// partway through.
var workerTeardown = []string{
	`REVOKE ibex_app FROM ibex_worker`,
	`REVOKE ibex_purge FROM ibex_worker`,
	`DROP OWNED BY ibex_worker`,
}

// assertMigrationRejectsForeignWorker rolls the migration suite back five
// steps, builds the case's worker shape, and requires 000064's
// capability-role-model abort. Cleanup is registered before setup and before Up
// so the roles a case created are removed even when setup fails partway through
// or the assertion fails. It is registered after the rollback: a failed Down
// leaves the migration state unknown, and dropping roles the migrations still
// own would turn one failure into a cross-test leak.
func assertMigrationRejectsForeignWorker(t *testing.T, tc foreignWorkerCase) {
	t.Helper()
	f := newTenancyFixture(t)
	ctx := t.Context()
	rewindToPreServiceModel(t, f)
	t.Cleanup(func() {
		revokes := append(append([]string{}, workerTeardown...), tc.revokes...)
		dropClusterRoles(context.Background(), f, revokes, tc.drops)
	})
	tc.setup(ctx, f)

	err := Up(f.dsn)
	if err == nil {
		t.Fatal("expected 000064 to reject the foreign worker")
	}
	for _, want := range []string{"pre-exists with a credential", "capability role model"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error does not mention %q: %v", want, err)
		}
	}
}

// dropClusterRoles revokes memberships then drops cluster-global roles.
func dropClusterRoles(ctx context.Context, f *tenancyFixture, revokes, drops []string) {
	execIgnoringError(ctx, f, append(append([]string{}, revokes...), drops...))
}

// execIgnoringError runs cleanup statements and discards their errors, so
// cleanup still completes after a failed assertion and tolerates the objects a
// partial fixture never created.
func execIgnoringError(ctx context.Context, f *tenancyFixture, statements []string) {
	for _, statement := range statements {
		_, _ = f.db.ExecContext(ctx, statement)
	}
}

// undoOnCleanup reverses a drift case's cluster-global change after its
// subtest. Roles, their attributes and their memberships live in the cluster
// rather than the database, so an unundone drift fails the next package's
// `provision` instead of the next assertion.
func undoOnCleanup(f *tenancyFixture, statements ...string) {
	f.t.Cleanup(func() {
		execIgnoringError(context.Background(), f, statements)
	})
}

// createdWorker returns the CREATE ROLE statement for an already provisioned
// ibex_worker. The salt byte keeps each test's verifier distinct.
func createdWorker(password string, saltByte byte) string {
	return fmt.Sprintf(`
		CREATE ROLE ibex_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
		NOBYPASSRLS NOINHERIT PASSWORD '%s'`,
		scramSHA256Verifier(scramInput{
			password: password, salt: bytes.Repeat([]byte{saltByte}, scramSaltBytes), iterations: scramIterations,
		}))
}

// TestMigrationRejectsPurgeMemberWorkerWithoutApp is the F3 lock. A role that
// already holds ibex_purge but was never made a member of ibex_app is
// necessarily hand-built: `migrate provision` requires both roles reachable and
// no migration grants ibex_purge to anything but the modelled pair. Reaching
// ibex_purge alone would satisfy a `pg_has_role(..., 'MEMBER')` provenance test,
// and the unconditional `GRANT ibex_app TO ibex_runtime, ibex_worker` would then
// hand that foreign role full tenant read/write on the branch the guard exists
// to abort, so 000064 requires both direct, SET-enabled memberships.
func TestMigrationRejectsPurgeMemberWorkerWithoutApp(t *testing.T) {
	assertMigrationRejectsForeignWorker(t, foreignWorkerCase{
		setup: func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `CREATE ROLE ibex_purge NOLOGIN NOINHERIT`)
			f.exec(ctx, createdWorker(testcreds.WorkerLoginTestPassword, 2))
			// Direct purge membership, no ibex_app membership: purge is
			// reachable, app is not, which is exactly the shape the
			// reachability test used to accept.
			f.exec(ctx, `GRANT ibex_purge TO ibex_worker`)
		},
		drops: []string{
			`DROP ROLE IF EXISTS ibex_worker`,
			`DROP ROLE IF EXISTS ibex_purge`,
		},
	})
}

// TestMigrationRejectsTransitiveMemberWorker is the F2 lock: reachability is
// not provenance. A bridge role holds ibex_app and ibex_purge, and ibex_worker
// reaches both only through it. `pg_has_role(..., 'MEMBER')` would accept that
// shape — and `migrate provision` would too, because it checks reachability by
// any path — but 000064's model is a direct, SET-enabled grant, so the worker
// is foreign and must abort. Reverting the predicate to pg_has_role re-opens
// the widening path and fails this test.
func TestMigrationRejectsTransitiveMemberWorker(t *testing.T) {
	assertMigrationRejectsForeignWorker(t, foreignWorkerCase{
		setup: func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `CREATE ROLE ibex_purge NOLOGIN NOINHERIT`)
			f.exec(ctx, `CREATE ROLE ibex_bridge NOLOGIN NOINHERIT`)
			f.exec(ctx, createdWorker(testcreds.WorkerLoginTestPassword, 3))
			// ibex_worker holds no direct capability row: both reach only
			// through the bridge, which is the shape a reachability predicate
			// accepts.
			f.exec(ctx, `GRANT ibex_app TO ibex_bridge`)
			f.exec(ctx, `GRANT ibex_purge TO ibex_bridge`)
			f.exec(ctx, `GRANT ibex_bridge TO ibex_worker`)
		},
		revokes: []string{
			`REVOKE ibex_bridge FROM ibex_worker`,
			`REVOKE ibex_app FROM ibex_bridge`,
			`REVOKE ibex_purge FROM ibex_bridge`,
			`DROP OWNED BY ibex_bridge`,
		},
		drops: []string{
			`DROP ROLE IF EXISTS ibex_worker`,
			`DROP ROLE IF EXISTS ibex_bridge`,
			`DROP ROLE IF EXISTS ibex_purge`,
		},
	})
}

// TestMigrationRejectsSetFalseMemberWorker is the SET-option lock. The worker
// holds direct rows for both capabilities, but each was granted WITH SET FALSE:
// a NOINHERIT login cannot assume them, so the rows describe a narrowed
// membership rather than provenance from this model. The unconditional GRANT
// below the guard would flip set_option back to true and silently widen it.
// Removing `AND m.set_option` re-opens that path and fails this test.
func TestMigrationRejectsSetFalseMemberWorker(t *testing.T) {
	assertMigrationRejectsForeignWorker(t, foreignWorkerCase{
		setup: func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `CREATE ROLE ibex_purge NOLOGIN NOINHERIT`)
			f.exec(ctx, createdWorker(testcreds.WorkerLoginTestPassword, 4))
			// Direct rows that exist but cannot be assumed: the exact shape the
			// bare EXISTS predicate accepted.
			f.exec(ctx, `GRANT ibex_app TO ibex_worker WITH SET FALSE`)
			f.exec(ctx, `GRANT ibex_purge TO ibex_worker WITH SET FALSE`)
		},
		drops: []string{
			`DROP ROLE IF EXISTS ibex_worker`,
			`DROP ROLE IF EXISTS ibex_purge`,
		},
	})
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
			testcreds.SetProvisionEnv(t)
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
// Each case undoes its cluster-global change on cleanup: a leftover membership
// or attribute is visible to every later package, which provisions the same
// roles, so it would fail them instead of failing here.
func driftCases() []driftCase {
	return []driftCase{
		{"unsafe attributes", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `ALTER ROLE ibex_runtime SUPERUSER`)
			undoOnCleanup(f, `ALTER ROLE ibex_runtime NOSUPERUSER`)
		}},
		{"direct forbidden", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `GRANT ibex_service TO ibex_runtime`)
			undoOnCleanup(f, `REVOKE ibex_service FROM ibex_runtime`)
		}},
		{"indirect forbidden", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `CREATE ROLE drift_bridge NOLOGIN`)
			f.exec(ctx, `GRANT ibex_service TO drift_bridge`)
			f.exec(ctx, `GRANT drift_bridge TO ibex_runtime`)
			undoOnCleanup(f,
				`REVOKE drift_bridge FROM ibex_runtime`,
				`DROP OWNED BY drift_bridge`,
				`DROP ROLE IF EXISTS drift_bridge`,
			)
		}},
		{"missing required", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `REVOKE ibex_app FROM ibex_runtime`)
			undoOnCleanup(f, `GRANT ibex_app TO ibex_runtime`)
		}},
		{"expired credential", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `ALTER ROLE ibex_runtime VALID UNTIL '2000-01-01'`)
			// 'infinity' is the natural no-expiry value, but lib/pq cannot scan
			// it into a time.Time and Provision fails on that scan, so the undo
			// uses a finite far-future date instead.
			undoOnCleanup(f, `ALTER ROLE ibex_runtime VALID UNTIL '2099-01-01T00:00:00Z'`)
		}},
		{"bootstrap tenant drift", func(ctx context.Context, f *tenancyFixture) {
			f.exec(ctx, `GRANT ibex_app TO ibex_bootstrap`)
			undoOnCleanup(f, `REVOKE ibex_app FROM ibex_bootstrap`)
		}},
		{"auth reaching runtime", func(ctx context.Context, f *tenancyFixture) {
			// Both logins hold ibex_app, so privilege alone cannot distinguish
			// them; the membership is refused because the capability model says
			// the auth login is not the runtime login and must not inherit what
			// ibex_runtime is granted later.
			f.exec(ctx, `GRANT ibex_runtime TO ibex_auth`)
			undoOnCleanup(f, `REVOKE ibex_runtime FROM ibex_auth`)
		}},
		{"auth reaching evidence relay", func(ctx context.Context, f *tenancyFixture) {
			// The relay identity claims the evidence outbox across
			// organizations. The auth login resolves one bearer and must never
			// carry that capability, so a stray membership is a provision-time
			// failure rather than a silent widening.
			f.exec(ctx, `GRANT ibex_evidence_relay TO ibex_auth`)
			undoOnCleanup(f, `REVOKE ibex_evidence_relay FROM ibex_auth`)
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
	for _, name := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_auth"} {
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
