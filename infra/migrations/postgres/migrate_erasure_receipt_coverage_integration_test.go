//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

// 000080 makes an erasure receipt record the addresses its proof covered.
//
// The column is deliberately nullable with no default: every receipt written
// before this migration recorded nothing about its coverage, and NULL means
// "covers no address", never "covers everything". A retry therefore stages a
// store whose current address the earlier receipt never proved.
const erasureReceiptCoverageVersion = 80

// TestErasureReceiptCoverage_ColumnShapeAndComment pins the three properties the
// consumer predicate depends on: the column exists, it is NULLable with no
// default (so an absent coverage is distinguishable from an empty proof), and
// the comment states what NULL means.
//
// Each property is asserted by one helper below, so a failure names the property
// that broke instead of the whole catalog row.
func TestErasureReceiptCoverage_ColumnShapeAndComment(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)

	column := readCoveredAddressesColumn(t, f)
	requireTextArray(t, column)
	requireNullable(t, column)
	requireNoDefault(t, column)
	requireCommentStatesNullCoversNoAddress(t, f)
}

// coveredAddressesColumn is the catalog row the consumer predicate resolves: the
// type the column must be, whether it is nullable, and whether it has a default.
type coveredAddressesColumn struct {
	dataType      string
	udtName       string
	isNullable    string
	columnDefault sql.NullString
}

// readCoveredAddressesColumn reads that row, failing the test if the column is
// absent from the catalog.
func readCoveredAddressesColumn(t *testing.T, f migrationFixture) coveredAddressesColumn {
	t.Helper()
	var column coveredAddressesColumn
	err := f.db.QueryRowContext(f.ctx, `
		SELECT data_type, is_nullable, udt_name, column_default
		  FROM information_schema.columns
		 WHERE table_schema = 'ibex_core'
		   AND table_name = 'erasure_store_receipts'
		   AND column_name = 'covered_addresses'`).
		Scan(&column.dataType, &column.isNullable, &column.udtName, &column.columnDefault)
	if err != nil {
		t.Fatalf("read covered_addresses column: %v", err)
	}
	return column
}

// requireTextArray asserts the column is a text array, which is the shape the
// consumer writes its locators into.
func requireTextArray(t *testing.T, column coveredAddressesColumn) {
	t.Helper()
	if column.dataType != "ARRAY" || column.udtName != "_text" {
		t.Fatalf("covered_addresses type = (%s, %s), want (ARRAY, _text)",
			column.dataType, column.udtName)
	}
}

// requireNullable asserts an absent coverage is representable: NULL means
// "covers no address", never "covers everything".
func requireNullable(t *testing.T, column coveredAddressesColumn) {
	t.Helper()
	if column.isNullable != "YES" {
		t.Fatalf("covered_addresses is_nullable = %s, want YES", column.isNullable)
	}
}

// requireNoDefault asserts a row that omits the column is not silently given a
// coverage: a default would turn an absent proof into a false one.
func requireNoDefault(t *testing.T, column coveredAddressesColumn) {
	t.Helper()
	if column.columnDefault.Valid {
		t.Fatalf("covered_addresses default = %q, want no default", column.columnDefault.String)
	}
}

// requireCommentStatesNullCoversNoAddress asserts the comment a reader of the
// schema finds states what NULL means.
func requireCommentStatesNullCoversNoAddress(t *testing.T, f migrationFixture) {
	t.Helper()
	var comment sql.NullString
	err := f.db.QueryRowContext(f.ctx, `
		SELECT col_description('ibex_core.erasure_store_receipts'::regclass, a.attnum)
		  FROM pg_attribute a
		 WHERE a.attrelid = 'ibex_core.erasure_store_receipts'::regclass
		   AND a.attname = 'covered_addresses'`).Scan(&comment)
	if err != nil {
		t.Fatalf("read covered_addresses comment: %v", err)
	}
	if !comment.Valid || !strings.Contains(comment.String, "covers no address") {
		t.Fatalf("covered_addresses comment = %q, want it to explain NULL covers no address",
			comment.String)
	}
}

// TestErasureReceiptCoverage_DownRefusesWhenCoverageExists pins the forward-only
// guard: dropping the column would delete the only record of which addresses a
// proof covered.
func TestErasureReceiptCoverage_DownRefusesWhenCoverageExists(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)
	requireTestRoleBypassesRLS(t, f.ctx, f.db)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertCoveredReceipt(t, f, coveredReceiptSeed{
		orgID:    orgA,
		memoryID: uuid.NewString(),
		covered:  []string{"s3://ibex-sessions/" + orgA + "/capture/full/1.json"},
	})

	requireDownRefused(t, f.ctx, f.db, downRefusal{
		file:    "000080_erasure_receipt_coverage.down.sql",
		message: "refusing destructive 000080 rollback",
	})
	requireVersion(t, f.dsn, f.head)
}

// erasureCapabilityRole is the identity the erasure worker writes receipts as,
// and the role the fenced-role test runs the down file as. It is `ibex_erasure`,
// not `ibex_app`: the down now takes `LOCK TABLE ... ACCESS EXCLUSIVE` before its
// guard, and that needs at least one of UPDATE, DELETE, or TRUNCATE on the table.
// 000075 leaves `ibex_app` with SELECT only (measured: LOCK TABLE as ibex_app
// fails with "permission denied for table erasure_store_receipts"), so `ibex_app`
// can no longer reach the code path that test exists to exercise. `ibex_erasure`
// holds SELECT and UPDATE and is still fenced by FORCE row level security.
const erasureCapabilityRole = "ibex_erasure"

// TestErasureReceiptCoverage_DownRefusesForARoleFencedByRLS proves the guard is
// not defeated by role attributes.
//
// The test above runs under the DSN's role, which bypasses RLS (asserted
// explicitly), so it proves the guard's message but not that the guard can still
// see rows. That is the deployment case the security review found: the table is
// ENABLE and FORCE row level security on `rls_org_visible(org_id)`, and a
// migration session sets neither the service identity nor an org GUC, so a
// non-superuser migrate role reads zero rows and the DROP proceeds.
//
// `SET row_security = off` in the down file turns that read into an error
// instead of a silent zero-row pass. This runs the real file as a capability
// role (NOLOGIN, NOSUPERUSER, NOBYPASSRLS) and first demonstrates the blind read,
// so the test would fail if the SET were removed.
func TestErasureReceiptCoverage_DownRefusesForARoleFencedByRLS(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertCoveredReceipt(t, f, coveredReceiptSeed{
		orgID:    orgA,
		memoryID: uuid.NewString(),
		covered:  []string{"s3://ibex-sessions/" + orgA + "/capture/full/1.json"},
	})

	// The blind spot, demonstrated: the same predicate as the guard sees no row.
	requireFencedReadSeesNoReceipts(t, f.ctx, f.db)

	downSQL, err := migrationFiles.ReadFile("000080_erasure_receipt_coverage.down.sql")
	if err != nil {
		t.Fatalf("read down file: %v", err)
	}
	tx, err := beginAsRole(f.ctx, f.db, erasureCapabilityRole)
	if err != nil {
		t.Fatalf("begin guarded down: %v", err)
	}
	// Rolled back even when the down unexpectedly succeeds, so a regression
	// cannot drop the column out from under the rest of the suite.
	defer func() { _ = tx.Rollback() }()
	_, err = tx.ExecContext(f.ctx, string(downSQL))
	if err == nil || !strings.Contains(err.Error(), "row-level security") {
		t.Fatalf("down as an RLS-fenced role error = %v, want a row-level security error", err)
	}

	requireVersion(t, f.dsn, f.head)
	requireCoveredAddressesColumn(t, f.ctx, f.db, true)
}

// beginAsRole begins a transaction switched to one allowlisted capability role.
// The caller owns the rollback: both callers must be able to discard everything
// the transaction did, because one of them executes a destructive down file.
func beginAsRole(ctx context.Context, db *sql.DB, roleName string) (*sql.Tx, error) {
	stmt, err := roleStatement(roleName)
	if err != nil {
		return nil, err
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, stmt); err != nil {
		_ = tx.Rollback()
		return nil, fmt.Errorf("set role %s: %w", roleName, err)
	}
	return tx, nil
}

// requireTestRoleBypassesRLS states the property the refusal test depends on.
//
// A refusal test that runs as a superuser proves the guard's message only; it
// cannot prove the guard sees the rows. Asserting the attribute makes a future
// change to POSTGRES_TEST_DSN visible instead of silently changing what the test
// demonstrates, and points at the test that covers the fenced case.
func requireTestRoleBypassesRLS(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	var role string
	var superuser, bypasses bool
	err := db.QueryRowContext(ctx, `
		SELECT current_user, rolsuper, rolbypassrls
		  FROM pg_roles WHERE rolname = current_user`).Scan(&role, &superuser, &bypasses)
	if err != nil {
		t.Fatalf("read current role attributes: %v", err)
	}
	if !superuser && !bypasses {
		t.Fatalf("test role %q is NEITHER rolsuper NOR rolbypassrls: this refusal "+
			"test proves the guard's message, which needs a role that can read every "+
			"tenant; the fenced case is covered by "+
			"TestErasureReceiptCoverage_DownRefusesForARoleFencedByRLS", role)
	}
}

// requireFencedReadSeesNoReceipts runs the guard's predicate as the fenced role
// with no org GUC and asserts the policy hides every seeded receipt from it.
func requireFencedReadSeesNoReceipts(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	var visible int
	tx, err := beginAsRole(ctx, db, erasureCapabilityRole)
	if err != nil {
		t.Fatalf("begin fenced read: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	err = tx.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM ibex_core.erasure_store_receipts
		 WHERE covered_addresses IS NOT NULL`).Scan(&visible)
	if err != nil {
		t.Fatalf("count receipts as %s: %v", erasureCapabilityRole, err)
	}
	if visible != 0 {
		t.Fatalf("%s without an org GUC sees %d covered receipt(s), want 0: "+
			"the policy is not fencing this read, so the test proves nothing",
			erasureCapabilityRole, visible)
	}
}

// TestErasureReceiptCoverage_CoverageIsInvisibleToAnotherTenant pins tenant
// isolation for the new column. `cache`/`cache_hot` locators carry `{org_id}`
// inside the value, so a loosened predicate would disclose another tenant's
// identifiers through `covered_addresses`, not just its row count.
func TestErasureReceiptCoverage_CoverageIsInvisibleToAnotherTenant(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)

	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	memoryA := uuid.NewString()
	locators := []string{
		"ibex:cache:memory:" + orgA + ":" + memoryA,
		"ibex:cache:hot:agent:" + orgA + ":scores",
	}
	insertCoveredReceipt(t, f, coveredReceiptSeed{
		orgID: orgA, memoryID: memoryA, covered: locators,
	})

	// Org A's own read sees the coverage.
	sameRows, sameCoverage := readCoverageAsTenant(t, f, coverageRead{
		orgID: orgA, memoryID: memoryA,
	})
	if sameRows != 1 {
		t.Fatalf("org A receipt rows = %d, want 1", sameRows)
	}
	if len(sameCoverage) != len(locators) {
		t.Fatalf("org A coverage = %v, want %v", sameCoverage, locators)
	}

	// Org B's read, with org A's memory id, sees neither the row nor the
	// addresses inside it.
	otherRows, otherCoverage := readCoverageAsTenant(t, f, coverageRead{
		orgID: orgB, memoryID: memoryA,
	})
	if otherRows != 0 {
		t.Fatalf("org B sees %d receipt row(s) for org A's memory, want 0", otherRows)
	}
	if len(otherCoverage) != 0 {
		t.Fatalf("org B read %v as org A coverage, want nothing", otherCoverage)
	}
}

// coverageRead is one tenant-scoped read of a memory's receipt coverage: the org
// a tenant query runs as and the memory it asks about, which are the two values
// a cross-tenant assertion varies.
type coverageRead struct {
	orgID    string
	memoryID string
}

// readCoverageAsTenant counts and reads one memory's receipt coverage as
// ibex_app scoped to read.orgID, which is the identity and GUC a tenant query
// uses.
func readCoverageAsTenant(
	t *testing.T, f migrationFixture, read coverageRead,
) (int, []string) {
	t.Helper()
	var rows int
	var coverage []string
	err := withAppRole(f.ctx, f.db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(f.ctx,
			`SELECT set_config('app.current_org_id', $1, true)`, read.orgID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(f.ctx, `
			SELECT COUNT(*) FROM ibex_core.erasure_store_receipts
			 WHERE memory_id = $1::uuid`, read.memoryID).Scan(&rows); err != nil {
			return err
		}
		if rows == 0 {
			return nil
		}
		var covered pq.StringArray
		if err := tx.QueryRowContext(f.ctx, `
			SELECT covered_addresses FROM ibex_core.erasure_store_receipts
			 WHERE memory_id = $1::uuid`, read.memoryID).Scan(&covered); err != nil {
			return err
		}
		coverage = append(coverage, covered...)
		return nil
	})
	if err != nil {
		t.Fatalf("read coverage as tenant %s: %v", read.orgID, err)
	}
	return rows, coverage
}

// TestErasureReceiptCoverage_DownIsSafeWhenCoverageIsNull proves the other half:
// a NULL coverage loses no information, so the rollback may proceed and a later
// up restores the column. The down is executed through the real migration
// runner, not a hand-copied statement.
func TestErasureReceiptCoverage_DownIsSafeWhenCoverageIsNull(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertErasureReceipt(t, f.ctx, f.db, erasureReceiptSeed{
		orgID:    orgA,
		memoryID: uuid.NewString(),
		revision: 2,
		store:    "objectstore",
	})

	downToVersion(t, f.dsn, erasureReceiptCoverageVersion-1)
	requireVersion(t, f.dsn, erasureReceiptCoverageVersion-1)
	requireCoveredAddressesColumn(t, f.ctx, f.db, false)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up after clean down: %v", err)
	}
	requireVersion(t, f.dsn, f.head)
	requireCoveredAddressesColumn(t, f.ctx, f.db, true)
}

func requireCoveredAddressesColumn(
	t *testing.T, ctx context.Context, db *sql.DB, want bool,
) {
	t.Helper()
	var present bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.columns
			WHERE table_schema = 'ibex_core'
			  AND table_name = 'erasure_store_receipts'
			  AND column_name = 'covered_addresses'
		)`).Scan(&present)
	if err != nil {
		t.Fatalf("check covered_addresses column: %v", err)
	}
	if present != want {
		t.Fatalf("covered_addresses present = %v, want %v", present, want)
	}
}

// coveredReceiptSeed is one verified receipt whose proof covered addresses.
type coveredReceiptSeed struct {
	orgID    string
	memoryID string
	covered  []string
}

// insertCoveredReceipt seeds that receipt as the owner.
func insertCoveredReceipt(t *testing.T, f migrationFixture, seed coveredReceiptSeed) {
	t.Helper()
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return insertCoveredReceiptIn(f.ctx, tx, seed)
	})
	if err != nil {
		t.Fatalf("insert covered receipt: %v", err)
	}
}

// insertCoveredReceiptIn writes that receipt inside a transaction the caller
// owns, so a test can leave it uncommitted on purpose.
func insertCoveredReceiptIn(ctx context.Context, tx *sql.Tx, seed coveredReceiptSeed) error {
	// nosemgrep: go_sql_rule-concat-sqli - literal statement with $N bind parameters; nothing is concatenated into the SQL.
	_, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.erasure_store_receipts
			(org_id, memory_id, revision, store, status, idempotency_key,
			 covered_addresses)
		VALUES ($1::uuid, $2::uuid, 2, 'objectstore', 'verified', $3, $4)`,
		seed.orgID, seed.memoryID, "coverage-"+seed.memoryID, pq.Array(seed.covered))
	return err
}

// downLockWaitBudget is how long a test waits to observe the down's request for
// ACCESS EXCLUSIVE. It stays below the down file's own `lock_timeout` of 5s, so a
// test that never sees the waiter fails on its own message rather than on a lock
// timeout.
const downLockWaitBudget = 3 * time.Second

// downLockPollInterval is how often that observation is retried.
const downLockPollInterval = 20 * time.Millisecond

// TestErasureReceiptCoverage_DownWaitsForAnInFlightWriter pins the lock that
// closes the window between the guard's read and the DROP COLUMN.
//
// The guard's `SELECT` on its own takes ACCESS SHARE, which does not conflict
// with the ROW EXCLUSIVE a worker holds while it commits its first non-NULL
// coverage. Without `LOCK TABLE ... ACCESS EXCLUSIVE` the sequence is: the guard
// reads nothing, the worker commits, `DROP COLUMN` then waits for that worker,
// is granted the lock once it is gone, and drops the only record of the addresses
// the worker proved absent. The window is driven deterministically here — the
// writer's insert stays uncommitted, the down is started, and the writer commits
// only once the down is observably queued for the table lock — so the test fails
// if the down reads before it locks.
func TestErasureReceiptCoverage_DownWaitsForAnInFlightWriter(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)
	requireTestRoleBypassesRLS(t, f.ctx, f.db)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)

	writerTx := beginInFlightErasureWrite(t, f, orgA)
	downSQL, err := migrationFiles.ReadFile("000080_erasure_receipt_coverage.down.sql")
	if err != nil {
		t.Fatalf("read down file: %v", err)
	}
	downDone := runDownInBackground(f, string(downSQL))

	requireDownBlockedOnReceiptsTable(t, f.ctx, f.db)
	if err := writerTx.Commit(); err != nil {
		t.Fatalf("commit the in-flight writer: %v", err)
	}

	err = <-downDone
	if err == nil || !strings.Contains(err.Error(), "refusing destructive 000080 rollback") {
		t.Fatalf("down error = %v, want the 000080 refusal: a coverage committed by a "+
			"writer that was in flight when the down started was not seen", err)
	}
	requireVersion(t, f.dsn, f.head)
	requireCoveredAddressesColumn(t, f.ctx, f.db, true)
}

// beginInFlightErasureWrite starts a receipt write as the erasure worker identity
// and leaves the transaction open, so the row is invisible to every other session
// until the test commits it.
func beginInFlightErasureWrite(t *testing.T, f migrationFixture, orgID string) *sql.Tx {
	t.Helper()
	tx, err := beginAsRole(f.ctx, f.db, erasureCapabilityRole)
	if err != nil {
		t.Fatalf("begin in-flight writer: %v", err)
	}
	t.Cleanup(func() { _ = tx.Rollback() })
	if _, err := tx.ExecContext(f.ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, orgID); err != nil {
		t.Fatalf("pin the writer's org: %v", err)
	}
	seed := coveredReceiptSeed{
		orgID:    orgID,
		memoryID: uuid.NewString(),
		covered:  []string{"s3://ibex-sessions/" + orgID + "/capture/full/in-flight.json"},
	}
	if err := insertCoveredReceiptIn(f.ctx, tx, seed); err != nil {
		t.Fatalf("in-flight covered receipt: %v", err)
	}
	return tx
}

// runDownInBackground executes the down file the same way golang-migrate does —
// the whole file in one zero-argument ExecContext — and returns its result.
func runDownInBackground(f migrationFixture, downSQL string) <-chan error {
	done := make(chan error, 1)
	go func() {
		_, err := f.db.ExecContext(f.ctx, downSQL)
		done <- err
	}()
	return done
}

// requireDownBlockedOnReceiptsTable waits until a session is queued for ACCESS
// EXCLUSIVE on the receipts table, which is the observable that proves the down
// asked for the lock. It fails rather than hangs when that never happens, so a
// down file that reads before it locks is reported instead of timing out.
func requireDownBlockedOnReceiptsTable(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	deadline := time.Now().Add(downLockWaitBudget)
	for time.Now().Before(deadline) {
		var waiters int
		err := db.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM pg_locks
			 WHERE relation = 'ibex_core.erasure_store_receipts'::regclass
			   AND mode = 'AccessExclusiveLock'
			   AND NOT granted`).Scan(&waiters)
		if err != nil {
			t.Fatalf("count lock waiters: %v", err)
		}
		if waiters > 0 {
			return
		}
		time.Sleep(downLockPollInterval)
	}
	t.Fatalf("no session waited for ACCESS EXCLUSIVE on ibex_core.erasure_store_receipts "+
		"within %s: the down does not take the lock before its guard", downLockWaitBudget)
}
