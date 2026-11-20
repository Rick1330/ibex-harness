//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"

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
func TestErasureReceiptCoverage_ColumnShapeAndComment(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)

	var dataType, isNullable, udtName string
	var columnDefault sql.NullString
	err := f.db.QueryRowContext(f.ctx, `
		SELECT data_type, is_nullable, udt_name, column_default
		  FROM information_schema.columns
		 WHERE table_schema = 'ibex_core'
		   AND table_name = 'erasure_store_receipts'
		   AND column_name = 'covered_addresses'`).
		Scan(&dataType, &isNullable, &udtName, &columnDefault)
	if err != nil {
		t.Fatalf("read covered_addresses column: %v", err)
	}
	if dataType != "ARRAY" || udtName != "_text" {
		t.Fatalf("covered_addresses type = (%s, %s), want (ARRAY, _text)", dataType, udtName)
	}
	if isNullable != "YES" {
		t.Fatalf("covered_addresses is_nullable = %s, want YES", isNullable)
	}
	if columnDefault.Valid {
		t.Fatalf("covered_addresses default = %q, want no default", columnDefault.String)
	}

	var comment sql.NullString
	err = f.db.QueryRowContext(f.ctx, `
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
	insertCoveredReceipt(t, f.ctx, f.db, orgA, uuid.NewString(),
		[]string{"s3://ibex-sessions/" + orgA + "/capture/full/1.json"})

	requireDownRefused(t, f.ctx, f.db, downRefusal{
		file:    "000080_erasure_receipt_coverage.down.sql",
		message: "refusing destructive 000080 rollback",
	})
	requireVersion(t, f.dsn, f.head)
}

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
// instead of a silent zero-row pass. This runs the real file as `ibex_app`
// (NOLOGIN, NOSUPERUSER, NOBYPASSRLS) and first demonstrates the blind read, so
// the test would fail if the SET were removed.
func TestErasureReceiptCoverage_DownRefusesForARoleFencedByRLS(t *testing.T) {
	f := newMigrationFixture(t, erasureReceiptCoverageVersion)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertCoveredReceipt(t, f.ctx, f.db, orgA, uuid.NewString(),
		[]string{"s3://ibex-sessions/" + orgA + "/capture/full/1.json"})

	// The blind spot, demonstrated: the same predicate as the guard sees no row.
	requireFencedReadSeesNoReceipts(t, f.ctx, f.db)

	downSQL, err := migrationFiles.ReadFile("000080_erasure_receipt_coverage.down.sql")
	if err != nil {
		t.Fatalf("read down file: %v", err)
	}
	tx, err := f.db.BeginTx(f.ctx, nil)
	if err != nil {
		t.Fatalf("begin guarded down: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(f.ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		t.Fatalf("set role ibex_app: %v", err)
	}
	_, err = tx.ExecContext(f.ctx, string(downSQL))
	if err == nil || !strings.Contains(err.Error(), "row-level security") {
		t.Fatalf("down as an RLS-fenced role error = %v, want a row-level security error", err)
	}

	requireVersion(t, f.dsn, f.head)
	requireCoveredAddressesColumn(t, f.ctx, f.db, true)
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

// requireFencedReadSeesNoReceipts runs the guard's predicate as ibex_app with no
// org GUC and asserts the policy hides every seeded receipt from it.
func requireFencedReadSeesNoReceipts(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	var visible int
	err := withAppRole(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_core.erasure_store_receipts
			 WHERE covered_addresses IS NOT NULL`).Scan(&visible)
	})
	if err != nil {
		t.Fatalf("count receipts as ibex_app: %v", err)
	}
	if visible != 0 {
		t.Fatalf("ibex_app without an org GUC sees %d covered receipt(s), want 0: "+
			"the policy is not fencing this read, so the test proves nothing", visible)
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
	insertCoveredReceipt(t, f.ctx, f.db, orgA, memoryA, locators)

	// Org A's own read sees the coverage.
	sameRows, sameCoverage := readCoverageAsTenant(t, f.ctx, f.db, orgA, memoryA)
	if sameRows != 1 {
		t.Fatalf("org A receipt rows = %d, want 1", sameRows)
	}
	if len(sameCoverage) != len(locators) {
		t.Fatalf("org A coverage = %v, want %v", sameCoverage, locators)
	}

	// Org B's read, with org A's memory id, sees neither the row nor the
	// addresses inside it.
	otherRows, otherCoverage := readCoverageAsTenant(t, f.ctx, f.db, orgB, memoryA)
	if otherRows != 0 {
		t.Fatalf("org B sees %d receipt row(s) for org A's memory, want 0", otherRows)
	}
	if len(otherCoverage) != 0 {
		t.Fatalf("org B read %v as org A coverage, want nothing", otherCoverage)
	}
}

// readCoverageAsTenant counts and reads one memory's receipt coverage as
// ibex_app scoped to orgID, which is the identity and GUC a tenant query uses.
func readCoverageAsTenant(
	t *testing.T, ctx context.Context, db *sql.DB, orgID, memoryID string,
) (int, []string) {
	t.Helper()
	var rows int
	var coverage []string
	err := withAppRole(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx,
			`SELECT set_config('app.current_org_id', $1, true)`, orgID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_core.erasure_store_receipts
			 WHERE memory_id = $1::uuid`, memoryID).Scan(&rows); err != nil {
			return err
		}
		if rows == 0 {
			return nil
		}
		var covered pq.StringArray
		if err := tx.QueryRowContext(ctx, `
			SELECT covered_addresses FROM ibex_core.erasure_store_receipts
			 WHERE memory_id = $1::uuid`, memoryID).Scan(&covered); err != nil {
			return err
		}
		coverage = append(coverage, covered...)
		return nil
	})
	if err != nil {
		t.Fatalf("read coverage as tenant %s: %v", orgID, err)
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

// insertCoveredReceipt seeds one verified receipt whose proof covered addresses.
func insertCoveredReceipt(
	t *testing.T, ctx context.Context, db *sql.DB,
	orgID, memoryID string, covered []string,
) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli - literal statement with $N bind parameters; nothing is concatenated into the SQL.
		_, execErr := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.erasure_store_receipts
				(org_id, memory_id, revision, store, status, idempotency_key,
				 covered_addresses)
			VALUES ($1::uuid, $2::uuid, 2, 'objectstore', 'verified', $3, $4)`,
			orgID, memoryID, "coverage-"+memoryID, pq.Array(covered))
		return execErr
	})
	if err != nil {
		t.Fatalf("insert covered receipt: %v", err)
	}
}
