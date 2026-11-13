//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"testing"
	"time"
)

// The migration suite runs against the database the operator configured in
// POSTGRES_TEST_DSN — in CI, the same `ibex` database `db-migrate-smoke` migrates
// a few steps earlier in the job.
//
// A per-run database (`ibex_test_<8 hex>`, created, migrated, leased, reaped and
// dropped by TestMain) was tried and has been deliberately removed. This is a
// correction of that design, recorded here rather than dropped silently, because
// the isolation it promised is not achievable in this cluster:
//
//   - PostgreSQL roles are cluster-global. The migrations create and drop
//     cluster-global roles (000004, 000036, 000064, 000068) and grant those roles
//     privileges on objects in the database they run in.
//   - `DROP ROLE` is resolved against the whole cluster, not the current
//     database. A second database that still holds those grants blocks the drop
//     with SQLSTATE 2BP01 ("role ... cannot be dropped because some objects
//     depend on it"), and the error names the *other* database.
//   - So every down migration in the per-run database failed while the migrated
//     `ibex` database still held the grants. The per-run database isolated the
//     schema and nothing else, and it broke the rollback tests that the schema
//     isolation was supposed to protect.
//
// What the harness actually needs — a run that an interrupted predecessor cannot
// poison — is a repair at the start of the run instead of a second database:
//
//   - resetSchemaConn drops the migrated schemas CASCADE, which removes every
//     object and every privilege the capability roles hold in *this* database,
//     and then drops the roles themselves. The role drops stay best effort: a
//     role another database in the same cluster still uses cannot be dropped
//     here, and the migration files' own idempotent guards (000004, 000036,
//     000064, 000068) normalise it on the way back up.
//   - Force(dsn, -1) clears a half-written or dirty `schema_migrations` row.
//     resetSchemaConn drops the table and golang-migrate re-creates it empty when
//     it opens the database, so Force(-1) truncates a table that exists instead
//     of failing on a missing one.
//
// Because the repair happens before the suite, a `SIGKILL`ed run costs the next
// run one reset instead of a manual cleanup.
//
// The harness never rewrites the DSN. There is no second database to point at,
// so no `dbname` or `database` query parameter is replaced: the DSN the operator
// wrote is the DSN the suite uses, and a parameter that names a database cannot
// be overridden behind their back.

// Harness modes, reported once per run so a CI log states which path executed.
const (
	modeSharedDatabase = "shared-database"
	modeUnavailable    = "unavailable"
)

// TestMain repairs the configured database before the suite executes.
func TestMain(m *testing.M) {
	os.Exit(runSharedDatabase(m))
}

// runSharedDatabase repairs the configured database and runs the suite against
// it.
//
// An unreachable database is reported and the suite runs anyway: every test
// skips through openTestDB, which is what a developer without Postgres expects.
// A database that is reachable but cannot be repaired is a failure, not a skip:
// continuing would run the suite against exactly the poisoned state this repair
// exists to remove.
func runSharedDatabase(m *testing.M) int {
	dsn := baseTestDSN()
	if err := pingDatabase(dsn); err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: %s (%v)\n", modeUnavailable, err)
		return m.Run()
	}
	if err := prepareSharedDatabase(dsn); err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: repair %s: %v\n", RedactedDSN(dsn), err)
		return 1
	}
	fmt.Fprintf(os.Stderr, "migration harness: %s %s\n", modeSharedDatabase, RedactedDSN(dsn))
	return m.Run()
}

// baseTestDSN is the DSN the operator configured, unchanged apart from the
// sslmode default lib/pq needs.
func baseTestDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return normalizePostgresDSN(dsn)
	}
	return defaultTestDSN
}

// pingDatabase reports whether dsn is reachable, with a bounded wait.
func pingDatabase(dsn string) error {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping %s: %w", RedactedDSN(dsn), err)
	}
	return nil
}

// prepareSharedDatabase is the recovery step: clear the schema and any dirty
// migration version so the suite starts from a known state even when a previous
// run was interrupted. It is called once by TestMain and directly by
// TestHarness_SharedDatabaseRecovery.
func prepareSharedDatabase(dsn string) error {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return fmt.Errorf("recovery open: %w", err)
	}
	defer func() { _ = db.Close() }()

	if err := resetSchemaConn(context.Background(), db); err != nil {
		return fmt.Errorf("recovery reset: %w", err)
	}
	// resetSchemaConn drops schema_migrations; Force(-1) re-creates it at the nil
	// version so a partially written version row cannot be inherited.
	if err := Force(dsn, -1); err != nil {
		return fmt.Errorf("recovery force -1: %w", err)
	}
	return nil
}

// TestHarness_SharedDatabaseRecovery proves the recovery step repairs a database
// an interrupted run left dirty: a recorded version marked dirty, which `Up`
// refuses, is cleared back to the newest embedded migration.
//
// It runs against the configured database rather than a scratch one on purpose.
// A second database holding the cluster-global capability roles is what made the
// per-run-database harness fail with SQLSTATE 2BP01, so exercising the repair on
// a second database would test the failure mode rather than the fix.
func TestHarness_SharedDatabaseRecovery(t *testing.T) {
	run := openSharedRun(t)
	run.up()
	run.markDirtyVersion()
	run.requireDirtyVersionRefused()
	run.recover()
	run.up()
	run.requireRecoveredVersion()
}

// sharedRun is one harness test's database: the DSN under test and the
// connection to it. Each step of the recovery scenario is a method so the test
// reads as the sequence it asserts.
type sharedRun struct {
	t   *testing.T
	dsn string
	db  *sql.DB
}

// openSharedRun opens the connection the scenario drives and closes it after the
// test.
func openSharedRun(t *testing.T) sharedRun {
	t.Helper()
	db := openTestDB(t)
	t.Cleanup(func() { _ = db.Close() })
	return sharedRun{t: t, dsn: testDSN(), db: db}
}

// up applies every migration, failing the test if the migration set refuses to
// run.
func (r sharedRun) up() {
	r.t.Helper()
	if err := Up(r.dsn); err != nil {
		r.t.Fatalf("up: %v", err)
	}
}

// markDirtyVersion simulates an interrupted run: a recorded version that the
// harness marked dirty before it stopped.
func (r sharedRun) markDirtyVersion() {
	r.t.Helper()
	if err := Force(r.dsn, 36); err != nil {
		r.t.Fatalf("force 36: %v", err)
	}
	if _, err := r.db.ExecContext(context.Background(), `UPDATE schema_migrations SET dirty = true`); err != nil {
		r.t.Fatalf("mark dirty: %v", err)
	}
}

// requireDirtyVersionRefused pins that Up refuses a dirty version: without that
// refusal the harness would inherit the dirty state instead of repairing it.
func (r sharedRun) requireDirtyVersionRefused() {
	r.t.Helper()
	if err := Up(r.dsn); err == nil {
		r.t.Fatal("up on a dirty version must fail; the harness would inherit the dirty state")
	}
}

// recover runs the recovery step the harness uses when a run finds a dirty
// database.
func (r sharedRun) recover() {
	r.t.Helper()
	if err := prepareSharedDatabase(r.dsn); err != nil {
		r.t.Fatalf("recovery: %v", err)
	}
}

// requireRecoveredVersion requires the recovered database to be clean and at the
// newest embedded migration.
func (r sharedRun) requireRecoveredVersion() {
	r.t.Helper()
	version, dirty, err := Version(r.dsn)
	if err != nil {
		r.t.Fatalf("version after recovery: %v", err)
	}
	if dirty {
		r.t.Fatal("recovered database is still dirty")
	}
	if want := maxEmbeddedMigrationVersion(r.t); version != want {
		r.t.Fatalf("version after recovery = %d, want %d", version, want)
	}
}
