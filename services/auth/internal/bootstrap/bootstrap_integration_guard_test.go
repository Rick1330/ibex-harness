//go:build integration

package bootstrap

import (
	"context"
	"database/sql"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/google/uuid"
)

// --- the second-organization guard's serialisation --------------------------

// TestBootstrapIntegrationRefusesSecondOrganization proves P2-13 against a real
// database: on an installation that already has an organization, a run whose
// slug is different mints nothing until IBEX_BOOTSTRAP_ALLOW_SECOND_ORG is set.
func TestBootstrapIntegrationRefusesSecondOrganization(t *testing.T) {
	f := newBootstrapFixture(t)
	first := f.run()

	second := f.cfg
	second.OrgSlug = uuid.NewString()
	second.UserEmail = "second-owner@example.com"
	second.MemoryToken = generatePAT(t)
	// The fixture sets the flag because the suite shares one database; the guard
	// is what this test is about, so it runs with the flag cleared.
	second.AllowSecondOrg = false
	t.Cleanup(func() { cleanupBootstrapOrg(t, f.db, second.OrgSlug) })

	_, err := bootstrap(context.Background(), f.db, second)
	if err == nil || !strings.Contains(err.Error(), "IBEX_BOOTSTRAP_ALLOW_SECOND_ORG=true") {
		t.Fatalf("second-organization bootstrap error = %v, want the guard refusal", err)
	}
	if orgs := countOrganizations(t, f.db, second.OrgSlug); orgs != 0 {
		t.Fatalf("refused run created %d organization(s) with slug %q, want 0", orgs, second.OrgSlug)
	}

	second.AllowSecondOrg = true
	allowed, err := bootstrap(context.Background(), f.db, second)
	if err != nil {
		t.Fatalf("bootstrap with IBEX_BOOTSTRAP_ALLOW_SECOND_ORG=true: %v", err)
	}
	if allowed.AlreadyBootstrapped {
		t.Fatal("the allowed second organization was reported as already bootstrapped")
	}
	if orgs := countOrganizations(t, f.db, second.OrgSlug); orgs != 1 {
		t.Fatalf("allowed run created %d organizations with slug %q, want 1", orgs, second.OrgSlug)
	}
	if first.OrgID == allowed.OrgID {
		t.Fatal("the second organization reused the first organization's id")
	}
}

// countOrganizations counts non-deleted organizations with one slug.
func countOrganizations(t *testing.T, db *sql.DB, slug string) int {
	t.Helper()
	var count int
	// nosemgrep: go_sql_rule-concat-sqli, go.lang.security.audit.sqli.gosql-sqli, go.lang.security.audit.sqli.gosql-sqli.gosql-sqli -- test fixture: the statement is a compile-time literal with one $1 placeholder and the slug is a bound argument, so no value reaches the SQL text.
	if err := db.QueryRowContext(context.Background(),
		`SELECT count(*) FROM ibex_core.organizations WHERE slug = $1 AND deleted_at IS NULL`,
		slug,
	).Scan(&count); err != nil {
		t.Fatalf("count organizations: %v", err)
	}
	return count
}

// scratchDatabasePattern is the exact shape of the scratch database name this
// file generates: the fixed ibex_scratch_ prefix and the 32 lowercase hex
// characters of a UUID. The DDL below only ever receives an identifier that
// matches it.
var scratchDatabasePattern = regexp.MustCompile(`^ibex_scratch_[0-9a-f]{32}$`)

// newScratchDatabaseName generates a scratch database name and refuses to hand
// out anything outside scratchDatabasePattern.
func newScratchDatabaseName(t *testing.T) string {
	t.Helper()
	name := "ibex_scratch_" + strings.ReplaceAll(uuid.NewString(), "-", "")
	if !scratchDatabasePattern.MatchString(name) {
		t.Fatalf("generated database name %q does not match %s", name, scratchDatabasePattern)
	}
	return name
}

// newScratchDatabase creates and migrates an empty database and returns its DSN.
//
// The guard decides about an installation that holds no organization, and the
// shared test database cannot offer that state: the whole suite writes into it.
// A scratch database gives the concurrent first runs a genuinely empty
// installation, and it is dropped with the test.
func newScratchDatabase(t *testing.T) string {
	t.Helper()
	shared, _ := testutil.SetupPostgres(t)
	admin, err := sql.Open("postgres", shared)
	if err != nil {
		t.Fatalf("open admin handle: %v", err)
	}
	name := newScratchDatabaseName(t)
	// nosemgrep: go_sql_rule-concat-sqli, go.lang.security.audit.sqli.gosql-sqli, go.lang.security.audit.sqli.gosql-sqli.gosql-sqli -- test fixture DDL: CREATE DATABASE takes an identifier rather than a bound parameter, and newScratchDatabaseName refused any name outside scratchDatabasePattern.
	if _, err := admin.Exec("CREATE DATABASE " + name); err != nil {
		_ = admin.Close()
		t.Fatalf("create scratch database: %v", err)
	}
	t.Cleanup(func() {
		// nosemgrep: go_sql_rule-concat-sqli, go.lang.security.audit.sqli.gosql-sqli, go.lang.security.audit.sqli.gosql-sqli.gosql-sqli -- test fixture DDL: DROP DATABASE takes an identifier rather than a bound parameter, and newScratchDatabaseName refused any name outside scratchDatabasePattern.
		if _, err := admin.Exec("DROP DATABASE IF EXISTS " + name + " WITH (FORCE)"); err != nil {
			t.Logf("drop scratch database %s: %v", name, err)
		}
		_ = admin.Close()
	})
	dsn := dsnForDatabase(t, shared, name)
	if err := postgres.Up(dsn); err != nil {
		t.Fatalf("migrate scratch database: %v", err)
	}
	return dsn
}

// dsnForDatabase points one Postgres DSN at another database on the same server.
func dsnForDatabase(t *testing.T, dsn, database string) string {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.Path = "/" + database
	return parsed.String()
}

// firstRunConfig is one first-run bootstrap aimed at a fresh installation, with
// the second-organization guard enabled: the guard is what these tests exercise.
// No memory-service bearer is supplied, so the run has to mint the organization
// and its token itself.
func firstRunConfig(t *testing.T, dsn, slug string) bootstrapConfig {
	t.Helper()
	cfg := newBootstrapConfig(t, dsn, slug, "owner@example.com")
	cfg.OrgName = "Concurrent " + slug
	return cfg
}

// runConcurrently starts every configuration at the same instant and returns
// each run's error in the order given.
func runConcurrently(t *testing.T, db *sql.DB, configs []bootstrapConfig) []error {
	t.Helper()
	errs := make([]error, len(configs))
	start := make(chan struct{})
	var wg sync.WaitGroup
	for index := range configs {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			<-start
			_, errs[index] = bootstrap(context.Background(), db, configs[index])
		}(index)
	}
	close(start)
	wg.Wait()
	return errs
}

// scratchHandle opens the scratch database the concurrency tests run against.
func scratchHandle(t *testing.T) (*sql.DB, string) {
	t.Helper()
	dsn := newScratchDatabase(t)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open scratch database: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db, dsn
}

// TestBootstrapIntegrationSerialisesConcurrentFirstRuns is the P2-13 race: two
// first runs against an installation that holds no organization must not both
// mint an owner credential. The guard's advisory lock makes its read-and-decide
// atomic, so one run creates the organization and the other refuses.
func TestBootstrapIntegrationSerialisesConcurrentFirstRuns(t *testing.T) {
	db, dsn := scratchHandle(t)
	configs := []bootstrapConfig{
		firstRunConfig(t, dsn, "concurrent-"+uuid.NewString()[:8]),
		firstRunConfig(t, dsn, "concurrent-"+uuid.NewString()[:8]),
	}

	errs := runConcurrently(t, db, configs)

	created := 0
	for index, err := range errs {
		switch {
		case err == nil:
			created++
		case strings.Contains(err.Error(), "IBEX_BOOTSTRAP_ALLOW_SECOND_ORG=true"):
			// The guard's refusal: the other run committed first.
		default:
			t.Fatalf("concurrent first run %d: %v", index, err)
		}
	}
	if created != 1 {
		t.Fatalf("%d of %d concurrent first runs created an organization, want exactly 1",
			created, len(configs))
	}
	total := countOrganizations(t, db, configs[0].OrgSlug) +
		countOrganizations(t, db, configs[1].OrgSlug)
	if total != 1 {
		t.Fatalf("the installation holds %d organizations for the two slugs, want 1", total)
	}
}

// holdGuardLockForTest takes the guard's advisory lock in a transaction the test owns,
// so a bootstrap call is forced to wait on it.
func holdGuardLockForTest(t *testing.T, db *sql.DB) *sql.Tx {
	t.Helper()
	holder, err := db.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("begin lock holder: %v", err)
	}
	// nosemgrep: go_sql_rule-concat-sqli, go.lang.security.audit.sqli.gosql-sqli, go.lang.security.audit.sqli.gosql-sqli.gosql-sqli -- test fixture: the statement is a compile-time literal with one $1 placeholder and guardLockKey is a bound argument, so no value reaches the SQL text.
	if _, err := holder.ExecContext(context.Background(),
		`SELECT true FROM pg_advisory_xact_lock($1)`, guardLockKey); err != nil {
		_ = holder.Rollback()
		t.Fatalf("take the guard lock: %v", err)
	}
	return holder
}

// startBootstrap runs a bootstrap on its own goroutine and reports the error.
func startBootstrap(db *sql.DB, cfg bootstrapConfig) <-chan error {
	done := make(chan error, 1)
	go func() {
		_, err := bootstrap(context.Background(), db, cfg)
		done <- err
	}()
	return done
}

// requireDecidesOnlyWhenUnlocked proves the bootstrap is still waiting while the
// guard lock is held, then releases the lock.
func requireDecidesOnlyWhenUnlocked(t *testing.T, done <-chan error, holder *sql.Tx) {
	t.Helper()
	select {
	case err := <-done:
		_ = holder.Rollback()
		t.Fatalf("bootstrap decided while another transaction held the guard lock (err = %v)", err)
	case <-time.After(400 * time.Millisecond):
	}
	if err := holder.Rollback(); err != nil {
		t.Fatalf("release the guard lock: %v", err)
	}
}

// requireDecidesAfterUnlock waits for the released bootstrap and fails when it
// refuses or never returns.
func requireDecidesAfterUnlock(t *testing.T, done <-chan error) {
	t.Helper()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("bootstrap after the guard lock was released: %v", err)
		}
	case <-time.After(verifyTimeout):
		t.Fatal("bootstrap did not decide after the guard lock was released")
	}
}

// TestBootstrapIntegrationWaitsForAnotherGuardLock pins the serialisation point
// itself: while another transaction holds the guard's advisory lock, a bootstrap
// must not decide. A guard that read the inventory without the lock would allow
// (or refuse) immediately, which is how two concurrent first runs both minted a
// credential.
func TestBootstrapIntegrationWaitsForAnotherGuardLock(t *testing.T) {
	db, dsn := scratchHandle(t)
	cfg := firstRunConfig(t, dsn, "blocked-"+uuid.NewString()[:8])

	holder := holdGuardLockForTest(t, db)
	done := startBootstrap(db, cfg)

	requireDecidesOnlyWhenUnlocked(t, done, holder)
	requireDecidesAfterUnlock(t, done)

	if got := countOrganizations(t, db, cfg.OrgSlug); got != 1 {
		t.Fatalf("the released run created %d organizations, want 1", got)
	}
}
