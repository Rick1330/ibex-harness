//go:build integration

package postgres

import (
	"context"
	"crypto/rand"
	"database/sql"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"testing"
	"time"
)

// P2-10: the migration suite was not hermetic.
//
// The integration tests used one shared database and dropped/re-created the
// schema per test. An interrupted run therefore poisoned the next one: the
// shared database kept a half-applied schema, a dirty `schema_migrations`
// version, and capability roles whose privileges in *other* databases made
// `DROP ROLE` fail. The next run then failed during its own cleanup instead of
// testing anything.
//
// This file isolates a run instead of a test:
//
//   - modePerRunDatabase (primary): TestMain reaps databases a killed run left
//     behind, creates `ibex_test_<8 hex>`, runs every migration once, executes
//     the suite against it, and drops it afterwards. Requires the DSN role to
//     hold CREATEDB (or superuser) on the maintenance database.
//   - modeSharedDatabase (fallback, when CREATE DATABASE is refused): TestMain
//     runs one `resetSchema` plus `Force(dsn, -1)` to clear a dirty version left
//     by an interrupted run, then the suite runs against the shared database as
//     before. Requires only the privileges the migrations already need.
//   - modeUnavailable: no reachable Postgres. Every test skips through
//     openTestDB, exactly as before.
//
// The mode is printed once per run so a CI log states which path executed.
//
// Roles are cluster-global in PostgreSQL, so a per-run database does not make
// them per-run. resetSchema therefore treats `DROP ROLE` as best effort: a role
// that another database still uses is left in place, and the migration files'
// own idempotent guards (000004, 000036, 000064, 000068) normalise it. That is
// the difference between a harness that recovers and one that aborts.
//
// Reaping is what closes the loop. A `SIGKILL`ed run cannot drop its database,
// and the orphan keeps cluster-global privileges for `ibex_service` /
// `ibex_evidence_relay`; the next run's *down* migrations then fail with SQLSTATE
// 2BP01 when they `DROP ROLE`. TestMain therefore drops every stale
// `ibex_test_<8 hex>` database before creating its own. The reap uses a plain
// `DROP DATABASE` (no FORCE), so it fails with `object_in_use` while a
// concurrent run is connected and leaves that run alone.

// Isolation modes reported by testRun.
const (
	modePerRunDatabase = "per-run-database"
	modeSharedDatabase = "shared-database"
	modeUnavailable    = "unavailable"
)

// maintenanceDatabase is the database TestMain connects to for CREATE DATABASE.
// It is never the database under test.
const maintenanceDatabase = "postgres"

// runDatabasePattern is the only shape a generated database name may take. The
// name is concatenated into CREATE/DROP DATABASE (PostgreSQL does not accept
// parameters there), so the shape is asserted before every statement.
var runDatabasePattern = regexp.MustCompile(`^ibex_test_[0-9a-f]{8}$`)

// testRun is the state TestMain publishes to the rest of the package.
var testRun struct {
	mode string
	dsn  string
	name string
	note string
}

// TestMain isolates the run before the suite executes.
func TestMain(m *testing.M) {
	os.Exit(runIsolated(m))
}

func runIsolated(m *testing.M) int {
	base := baseTestDSN()

	admin, err := openMaintenanceDB(base)
	if err != nil {
		testRun.mode = modeUnavailable
		testRun.note = err.Error()
		reportMode()
		return m.Run()
	}
	defer func() { _ = admin.Close() }()

	reapStaleRunDatabases(admin)

	name, err := createRunDatabase(admin)
	if err != nil {
		// Not permitted (or not supported): fall back to the shared database and
		// repair whatever an interrupted run left behind.
		testRun.mode = modeSharedDatabase
		testRun.note = err.Error()
		testRun.dsn = base
		prepareSharedDatabase(base)
		reportMode()
		return m.Run()
	}

	runDSN, err := dsnWithDatabase(base, name)
	if err != nil {
		_ = dropRunDatabase(admin, name)
		fmt.Fprintf(os.Stderr, "migration harness: rewrite dsn for %s: %v\n", name, err)
		return 1
	}

	testRun.mode = modePerRunDatabase
	testRun.name = name
	testRun.dsn = runDSN

	if err := Up(runDSN); err != nil {
		_ = dropRunDatabase(admin, name)
		fmt.Fprintf(os.Stderr, "migration harness: migrate %s: %v\n", name, err)
		return 1
	}

	reportMode()
	code := m.Run()
	if err := dropRunDatabase(admin, name); err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: drop database %s: %v\n", name, err)
	}
	return code
}

func reportMode() {
	switch testRun.mode {
	case modePerRunDatabase:
		fmt.Fprintf(os.Stderr, "migration harness: %s %s\n", testRun.mode, testRun.name)
	case modeSharedDatabase:
		fmt.Fprintf(os.Stderr, "migration harness: %s (CREATE DATABASE refused: %v)\n", testRun.mode, testRun.note)
	case modeUnavailable:
		fmt.Fprintf(os.Stderr, "migration harness: %s (%s)\n", testRun.mode, testRun.note)
	}
}

// baseTestDSN is the DSN the operator configured, before any per-run rewrite.
func baseTestDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return normalizePostgresDSN(dsn)
	}
	return defaultTestDSN
}

// openMaintenanceDB connects to the cluster's `postgres` database. That
// connection is used only for CREATE DATABASE / DROP DATABASE.
func openMaintenanceDB(base string) (*sql.DB, error) {
	adminDSN, err := dsnWithDatabase(base, maintenanceDatabase)
	if err != nil {
		return nil, fmt.Errorf("maintenance dsn: %w", err)
	}
	db, err := sql.Open("postgres", adminDSN)
	if err != nil {
		return nil, fmt.Errorf("open maintenance db: %w", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ping maintenance db %s: %w", RedactedDSN(adminDSN), err)
	}
	return db, nil
}

// dsnWithDatabase returns dsn pointed at database, preserving credentials and
// parameters. Only the URL form is supported; the key/value form is rejected
// so the caller falls back instead of guessing.
func dsnWithDatabase(dsn, database string) (string, error) {
	parsed, err := url.Parse(dsn)
	if err != nil {
		return "", fmt.Errorf("parse dsn: %w", err)
	}
	if parsed.Scheme != "postgres" && parsed.Scheme != "postgresql" {
		return "", fmt.Errorf("unsupported dsn scheme %q; expected postgres://", parsed.Scheme)
	}
	parsed.Path = "/" + database
	return parsed.String(), nil
}

// reapStaleRunDatabases drops per-run databases a killed run could not drop.
//
// Plain `DROP DATABASE` is deliberate: it fails with SQLSTATE 55006 while
// another session is connected, which is exactly the case where the database
// belongs to a concurrent run and must be left alone. FORCE is never used here.
func reapStaleRunDatabases(admin *sql.DB) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	names, err := staleRunDatabases(ctx, admin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: list stale databases: %v\n", err)
		return
	}
	for _, name := range names {
		if !runDatabasePattern.MatchString(name) {
			continue
		}
		if _, err := admin.ExecContext(ctx, "DROP DATABASE IF EXISTS "+name); err != nil {
			fmt.Fprintf(os.Stderr, "migration harness: keeping database %s (%v)\n", name, err)
			continue
		}
		fmt.Fprintf(os.Stderr, "migration harness: reaped stale database %s\n", name)
	}
}

func staleRunDatabases(ctx context.Context, admin *sql.DB) ([]string, error) {
	rows, err := admin.QueryContext(ctx, `
		SELECT datname FROM pg_database
		WHERE datname ~ '^ibex_test_[0-9a-f]{8}$'
		ORDER BY datname`)
	if err != nil {
		return nil, err
	}
	defer func() { _ = rows.Close() }()

	var names []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		names = append(names, name)
	}
	return names, rows.Err()
}

func createRunDatabase(admin *sql.DB) (string, error) {
	name, err := runDatabaseName()
	if err != nil {
		return "", fmt.Errorf("generate database name: %w", err)
	}
	if !runDatabasePattern.MatchString(name) {
		return "", fmt.Errorf("refusing unsafe database name %q", name)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if _, err := admin.ExecContext(ctx, "CREATE DATABASE "+name); err != nil {
		return "", fmt.Errorf("create database %s: %w", name, err)
	}
	return name, nil
}

// dropRunDatabase removes the per-run database. FORCE terminates connections a
// failed test left open; it needs PostgreSQL 13+ and is retried without it.
func dropRunDatabase(admin *sql.DB, name string) error {
	if !runDatabasePattern.MatchString(name) {
		return fmt.Errorf("refusing unsafe database name %q", name)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if _, err := admin.ExecContext(ctx, "DROP DATABASE IF EXISTS "+name+" WITH (FORCE)"); err == nil {
		return nil
	}
	_, err := admin.ExecContext(ctx, "DROP DATABASE IF EXISTS "+name)
	return err
}

func runDatabaseName() (string, error) {
	var suffix [4]byte
	if _, err := rand.Read(suffix[:]); err != nil {
		return "", err
	}
	return fmt.Sprintf("ibex_test_%x", suffix), nil
}

// prepareSharedDatabase is the fallback recovery path: clear the schema and any
// dirty migration version so the suite starts from a known state even when a
// previous run was interrupted.
func prepareSharedDatabase(dsn string) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: fallback recovery open: %v\n", err)
		return
	}
	defer func() { _ = db.Close() }()

	if err := resetSchemaConn(context.Background(), db); err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: fallback recovery reset: %v\n", err)
		return
	}
	// resetSchemaConn drops schema_migrations; Force(-1) re-creates it at the nil
	// version so a partially written version row cannot be inherited.
	if err := Force(dsn, -1); err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: fallback recovery force -1: %v\n", err)
	}
}

// TestHarness_SharedDatabaseRecovery proves the fallback path repairs a
// database an interrupted run left dirty. The mode itself is not reachable on a
// cluster where the migration role is superuser (CREATE EXTENSION vector needs
// it, and a superuser can always CREATE DATABASE), so the recovery step is
// exercised directly instead of through mode selection.
//
// It runs against the run database rather than a scratch one on purpose: a
// second database holding the cluster-global capability roles makes the *down*
// migrations fail with SQLSTATE 2BP01, which is the same failure mode this file
// exists to remove.
func TestHarness_SharedDatabaseRecovery(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer func() { _ = db.Close() }()

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	// Simulate an interrupted run: a recorded version marked dirty.
	if err := Force(dsn, 36); err != nil {
		t.Fatalf("force 36: %v", err)
	}
	if _, err := db.ExecContext(context.Background(), `UPDATE schema_migrations SET dirty = true`); err != nil {
		t.Fatalf("mark dirty: %v", err)
	}
	if err := Up(dsn); err == nil {
		t.Fatal("up on a dirty version must fail; the harness would inherit the dirty state")
	}

	prepareSharedDatabase(dsn)

	if err := Up(dsn); err != nil {
		t.Fatalf("up after recovery: %v", err)
	}
	version, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version after recovery: %v", err)
	}
	if dirty {
		t.Fatal("recovered database is still dirty")
	}
	if want := maxEmbeddedMigrationVersion(t); version != want {
		t.Fatalf("version after recovery = %d, want %d", version, want)
	}
}
