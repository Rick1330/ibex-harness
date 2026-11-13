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
	"strconv"
	"strings"
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
// `ibex_test_<8 hex>` database before creating its own.
//
// A reap must never destroy a concurrent run's database, and "a plain DROP fails
// while another session is connected" does not achieve that: between another
// run's CREATE DATABASE and its first session there is no connection to fail on,
// so the DROP succeeds and the victim then either fails in Up or silently skips,
// because openTestDB turns a ping failure into t.Skipf. Two advisory locks close
// that window:
//
//   - reapLockKey is taken before the reap and released once this run's database
//     exists. Reap and create are therefore one critical section, so a reaper
//     never sees a database whose owner has not leased it yet, and only one run
//     scans and drops at a time.
//   - runLeaseKey(<name>) is taken by a run *before* it creates its database and
//     held until it drops it. The reaper drops a database only when it can take
//     that lease, so "does a live run own this database?" is answerable at any
//     instant, including the create-to-first-session gap.
//
// Advisory locks are cluster-global and session-scoped: PostgreSQL releases them
// when the session ends, so a killed run cannot leave either lock held. A run
// that cannot take the reap lock reaps nothing and proceeds — its own database is
// protected by its lease, not by the reap lock — and a later run collects the
// orphan. The consequence is stated rather than hidden: skipping the reap can
// leave an orphan behind that makes a *down* migration in that run fail with
// 2BP01. That failure is loud and retryable; destroying a live run's database is
// silent.

// Isolation modes reported by testRun.
const (
	modePerRunDatabase = "per-run-database"
	modeSharedDatabase = "shared-database"
	modeUnavailable    = "unavailable"
)

// maintenanceDatabase is the database TestMain connects to for CREATE DATABASE.
// It is never the database under test.
const maintenanceDatabase = "postgres"

// runDatabasePrefix is the fixed part of every per-run database name.
const runDatabasePrefix = "ibex_test_"

// runDatabasePattern is the only shape a generated database name may take. The
// name is concatenated into CREATE/DROP DATABASE (PostgreSQL does not accept
// parameters there), so the shape is asserted before every statement.
var runDatabasePattern = regexp.MustCompile("^" + runDatabasePrefix + `[0-9a-f]{8}$`)

// Advisory-lock keys. A key is a 64-bit integer built from a fixed tag (0x1B3E,
// deliberately unusual), a 16-bit purpose word, and — for a per-run database
// lease — the database name's 32 random bits:
//
//	0x1B3E_0002_00000000  reap lock, no suffix
//	0x1B3E_0001_xxxxxxxx  lease of ibex_test_xxxxxxxx
//
// The tag cannot collide with pgprovision's bare 0x69626578 key, and the purpose
// word keeps the harness's own two keys apart, so no lease can ever equal the
// reap lock. Both keys are cluster-global and session-scoped: PostgreSQL releases
// them when the session ends, so a killed run cannot leave one held.
const (
	// lockPurposeLease tags a per-run database lease.
	lockPurposeLease int64 = 0x1B3E0001
	// lockPurposeReap tags the cluster-wide reap lock.
	lockPurposeReap int64 = 0x1B3E0002

	// reapLockKey serialises reap and create across runs.
	reapLockKey int64 = lockPurposeReap << 32

	// runDatabaseAttempts bounds the name/lease retry loop. A collision needs two
	// runs to draw the same 32 random bits, or a reaper to be mid-drop of that
	// exact name, so the first attempt succeeds in practice; the bound keeps a
	// pathological cluster from looping forever.
	runDatabaseAttempts = 8
)

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

	// Reap and create are one critical section: a reaper must never see a
	// database another run has created but not yet leased. The lock is released
	// as soon as this run's database exists, because from then on the database is
	// protected by its own lease.
	reapLock, lockErr := tryAdvisoryLock(admin, reapLockKey)
	switch {
	case lockErr != nil:
		fmt.Fprintf(os.Stderr, "migration harness: reap lock unavailable (%v); not reaping\n", lockErr)
	case !reapLock.held:
		fmt.Fprintln(os.Stderr, "migration harness: another run is reaping; not reaping")
	default:
		reapStaleRunDatabases(admin)
	}

	name, lease, err := createRunDatabase(admin)
	reapLock.release()
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
	defer lease.release()

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

// advisoryLock is one session-scoped PostgreSQL advisory lock. It is taken on a
// pinned connection because a lock belongs to the session that took it, and a
// *sql.DB hands out a different session per statement.
type advisoryLock struct {
	conn *sql.Conn
	key  int64
	held bool
}

// tryAdvisoryLock takes key without waiting. A lock that is not taken is not an
// error: it means another session owns what the key protects.
func tryAdvisoryLock(admin *sql.DB, key int64) (advisoryLock, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, err := admin.Conn(ctx)
	if err != nil {
		return advisoryLock{}, fmt.Errorf("advisory lock %#x connection: %w", key, err)
	}
	var held bool
	// nosemgrep: go_sql_rule-concat-sqli -- constant advisory-lock statement; the key is a bound parameter.
	if err := conn.QueryRowContext(ctx, `SELECT pg_try_advisory_lock($1)`, key).Scan(&held); err != nil {
		_ = conn.Close()
		return advisoryLock{}, fmt.Errorf("advisory lock %#x: %w", key, err)
	}
	if !held {
		_ = conn.Close()
		return advisoryLock{}, nil
	}
	return advisoryLock{conn: conn, key: key, held: true}, nil
}

// release unlocks and returns the session. It is safe on the zero value, so a
// caller can defer it unconditionally. A killed process needs no release:
// PostgreSQL drops a session's locks with the session.
func (l advisoryLock) release() {
	if !l.held {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	var unlocked bool
	// nosemgrep: go_sql_rule-concat-sqli -- constant advisory-unlock statement; the key is a bound parameter.
	_ = l.conn.QueryRowContext(ctx, `SELECT pg_advisory_unlock($1)`, l.key).Scan(&unlocked)
	_ = l.conn.Close()
}

// reapStaleRunDatabases drops the per-run databases no live run owns.
//
// Ownership is a lease, not a connection count. A plain `DROP DATABASE` only
// fails while another session is connected, and between another run's CREATE
// DATABASE and its first session there is nothing to fail on, so the DROP
// succeeded and destroyed a live run. reapRunDatabase therefore drops a database
// only when it can take that database's lease. FORCE is never used here.
func reapStaleRunDatabases(admin *sql.DB) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	names, err := staleRunDatabases(ctx, admin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: list stale databases: %v\n", err)
		return
	}
	for _, name := range names {
		reapRunDatabase(admin, name)
	}
}

// reapRunDatabase drops name only if no live run holds its lease.
func reapRunDatabase(admin *sql.DB, name string) {
	if !runDatabasePattern.MatchString(name) {
		return
	}
	key, err := runLeaseKey(name)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: keeping database %s (%v)\n", name, err)
		return
	}
	lease, err := tryAdvisoryLock(admin, key)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: keeping database %s (lease unavailable: %v)\n", name, err)
		return
	}
	if !lease.held {
		fmt.Fprintf(os.Stderr, "migration harness: keeping database %s (owned by a live run)\n", name)
		return
	}
	defer lease.release()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if _, err := admin.ExecContext(ctx, "DROP DATABASE IF EXISTS "+name); err != nil {
		fmt.Fprintf(os.Stderr, "migration harness: keeping database %s (%v)\n", name, err)
		return
	}
	fmt.Fprintf(os.Stderr, "migration harness: reaped stale database %s\n", name)
}

func staleRunDatabases(ctx context.Context, admin *sql.DB) ([]string, error) {
	rows, err := admin.QueryContext(ctx, `
		SELECT datname FROM pg_database
		WHERE datname ~ $1
		ORDER BY datname`, runDatabasePattern.String())
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

// createRunDatabase creates the per-run database and returns the lease that keeps
// a concurrent reaper away.
//
// The lease is taken before CREATE DATABASE, so a database that exists always has
// an owner that already announced itself: a reaper can never observe the gap
// between creation and ownership.
func createRunDatabase(admin *sql.DB) (string, advisoryLock, error) {
	var lastErr error
	for attempt := 0; attempt < runDatabaseAttempts; attempt++ {
		name, err := runDatabaseName()
		if err != nil {
			return "", advisoryLock{}, fmt.Errorf("generate database name: %w", err)
		}
		lease, err := leaseRunDatabase(admin, name)
		if err != nil {
			return "", advisoryLock{}, err
		}
		if !lease.held {
			// Another session holds this name: a reaper mid-drop, or a run that
			// drew the same 32 random bits. Draw again.
			lastErr = fmt.Errorf("lease of %s is held by another session", name)
			continue
		}
		if err := createDatabase(admin, name); err != nil {
			lease.release()
			return "", advisoryLock{}, err
		}
		return name, lease, nil
	}
	return "", advisoryLock{}, fmt.Errorf("no free run database name in %d attempts: %w", runDatabaseAttempts, lastErr)
}

// leaseRunDatabase takes name's lease, so a reaper that scans between this call
// and CREATE DATABASE already sees the database as owned.
func leaseRunDatabase(admin *sql.DB, name string) (advisoryLock, error) {
	key, err := runLeaseKey(name)
	if err != nil {
		return advisoryLock{}, err
	}
	lease, err := tryAdvisoryLock(admin, key)
	if err != nil {
		return advisoryLock{}, fmt.Errorf("lease database %s: %w", name, err)
	}
	return lease, nil
}

// createDatabase runs CREATE DATABASE after re-asserting the name's shape.
func createDatabase(admin *sql.DB, name string) error {
	if !runDatabasePattern.MatchString(name) {
		return fmt.Errorf("refusing unsafe database name %q", name)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if _, err := admin.ExecContext(ctx, "CREATE DATABASE "+name); err != nil {
		return fmt.Errorf("create database %s: %w", name, err)
	}
	return nil
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

// runDatabaseName returns a fresh per-run database name.
func runDatabaseName() (string, error) {
	var suffix [4]byte
	if _, err := rand.Read(suffix[:]); err != nil {
		return "", err
	}
	return fmt.Sprintf("%s%x", runDatabasePrefix, suffix), nil
}

// runLeaseKey is the advisory-lock key that leases name: the lease purpose word
// in the high 32 bits and the name's random suffix in the low 32 bits, so the key
// is unique per database and can be recomputed from the name alone.
func runLeaseKey(name string) (int64, error) {
	if !runDatabasePattern.MatchString(name) {
		return 0, fmt.Errorf("refusing unsafe database name %q", name)
	}
	suffix, err := strconv.ParseUint(strings.TrimPrefix(name, runDatabasePrefix), 16, 32)
	if err != nil {
		return 0, fmt.Errorf("parse suffix of %s: %w", name, err)
	}
	return lockPurposeLease<<32 | int64(suffix), nil
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
	run := openSharedRun(t)
	run.up()
	run.markDirtyVersion()
	run.requireDirtyVersionRefused()
	run.recover()
	run.up()
	run.requireRecoveredVersion()
}

// TestHarness_Reaper_LeavesConcurrentRunAlone reproduces the window that made the
// old reaper destructive: a run has created its database and has not connected to
// it yet, so a plain DROP DATABASE had nothing to fail on and the victim either
// failed in Up or skipped silently through openTestDB.
//
// The reaper is called directly, so the test proves the reaper's own rule rather
// than the order TestMain happens to run in. All three parts of the fix are
// asserted: the reap lock excludes a second session, a reap that runs anyway
// leaves a leased database alone, and the same reap still collects a database
// nobody owns.
func TestHarness_Reaper_LeavesConcurrentRunAlone(t *testing.T) {
	admin, err := openMaintenanceDB(baseTestDSN())
	if err != nil {
		t.Skipf("maintenance database not available: %v", err)
	}
	defer func() { _ = admin.Close() }()

	// The concurrent run: lease, then CREATE DATABASE, and never connect.
	name, lease, err := createRunDatabase(admin)
	if err != nil {
		t.Skipf("per-run database not available: %v", err)
	}
	t.Cleanup(func() {
		_ = dropRunDatabase(admin, name)
		lease.release()
	})

	reapLock, err := tryAdvisoryLock(admin, reapLockKey)
	if err != nil {
		t.Fatalf("take reap lock: %v", err)
	}
	if !reapLock.held {
		t.Fatal("reap lock is not held; the reap+create critical section is open")
	}
	second, err := tryAdvisoryLock(admin, reapLockKey)
	if err != nil {
		t.Fatalf("second reap lock attempt: %v", err)
	}
	if second.held {
		t.Fatal("a second session took the reap lock; reap and create can interleave")
	}

	reapStaleRunDatabases(admin)
	requireDatabaseExists(t, admin, name)
	reapLock.release()

	// Positive control: once the lease is gone the same reap does collect it.
	lease.release()
	reapStaleRunDatabases(admin)
	requireDatabaseDropped(t, admin, name)
}

// requireDatabaseExists fails if name is not in pg_database.
func requireDatabaseExists(t *testing.T, admin *sql.DB, name string) {
	t.Helper()
	if !databaseExists(t, admin, name) {
		t.Fatalf("database %s was destroyed by the reaper; a concurrent run owns it", name)
	}
}

// requireDatabaseDropped fails if name is still in pg_database.
func requireDatabaseDropped(t *testing.T, admin *sql.DB, name string) {
	t.Helper()
	if databaseExists(t, admin, name) {
		t.Fatalf("database %s survived a reap; the reaper no longer collects orphans", name)
	}
}

// databaseExists reports whether name is in pg_database.
func databaseExists(t *testing.T, admin *sql.DB, name string) bool {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	var exists bool
	if err := admin.QueryRowContext(ctx,
		`SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = $1)`, name).Scan(&exists); err != nil {
		t.Fatalf("check database %s: %v", name, err)
	}
	return exists
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

// recover runs the fallback recovery path the harness uses when a run finds a
// dirty database.
func (r sharedRun) recover() {
	r.t.Helper()
	prepareSharedDatabase(r.dsn)
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
