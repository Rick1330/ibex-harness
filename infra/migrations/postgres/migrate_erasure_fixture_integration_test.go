//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// migrationFixture is one freshly migrated schema plus the handles the erasure
// migration tests assert against.
//
// Every test in this pair needs the same "drop everything, migrate to head"
// preamble. Repeating it eight lines at a time is how two tests silently stop
// proving the same thing, so it lives here once and takes the version the caller
// asserts against.
type migrationFixture struct {
	dsn  string
	db   *sql.DB
	ctx  context.Context
	head uint
}

// newMigrationFixture resets the schema, migrates to head, and returns the
// handles. headVersion is the version the calling test asserts against.
func newMigrationFixture(t *testing.T, headVersion uint) migrationFixture {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	t.Cleanup(func() { _ = db.Close() })
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	return migrationFixture{
		dsn:  dsn,
		db:   db,
		ctx:  context.Background(),
		head: requireHeadVersionAtLeast(t, dsn, headVersion),
	}
}

// erasureReceiptSeed is one erasure_store_receipts row the tests seed as the
// owner.
type erasureReceiptSeed struct {
	orgID    string
	memoryID string
	revision int64
	store    string
}

// insertErasureReceipt seeds one verified receipt as the owner.
func insertErasureReceipt(t *testing.T, ctx context.Context, db *sql.DB, seed erasureReceiptSeed) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.erasure_store_receipts
				(org_id, memory_id, revision, store, status, idempotency_key)
			VALUES ($1::uuid, $2::uuid, $3, $4, 'verified', $5)`,
			seed.orgID, seed.memoryID, seed.revision, seed.store,
			"erase-"+seed.memoryID+"-"+seed.store)
		return execErr
	})
	if err != nil {
		t.Fatalf("insert erasure receipt: %v", err)
	}
}

// tenantPair is the two tenants a cross-tenant assertion needs, so the helpers
// that check both keep a single scope argument.
type tenantPair struct {
	orgA, orgB string
}

// outboxSeed is one memory_lifecycle_outbox row a test seeds as the owner.
type outboxSeed struct {
	orgID        string
	memoryID     string
	revision     int64
	erasureState string
}

// insertOutboxRow seeds one outbox row, failing the test if the insert is refused.
func insertOutboxRow(t *testing.T, ctx context.Context, db *sql.DB, seed outboxSeed) {
	t.Helper()
	if err := insertOutboxWithState(ctx, db, seed); err != nil {
		t.Fatalf("insert outbox row: %v", err)
	}
}

// insertOutboxWithState seeds one outbox row with an explicit erasure_state and
// returns the error, so a test can assert the closed domain rejects a value.
func insertOutboxWithState(ctx context.Context, db *sql.DB, seed outboxSeed) error {
	return withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memory_lifecycle_outbox
				(org_id, memory_id, revision, event_type, erasure_state)
			VALUES ($1::uuid, $2::uuid, $3, 'forgotten', $4)`,
			seed.orgID, seed.memoryID, seed.revision, seed.erasureState)
		return execErr
	})
}

// seedPendingOutboxRow seeds one pending row for a tenant and returns its memory id.
func seedPendingOutboxRow(t *testing.T, ctx context.Context, db *sql.DB, orgID string) string {
	t.Helper()
	memoryID := uuid.NewString()
	insertOutboxRow(t, ctx, db, outboxSeed{
		orgID: orgID, memoryID: memoryID, revision: 2, erasureState: "pending",
	})
	return memoryID
}

// downRefusal is one down file and the message its guard must raise.
type downRefusal struct {
	file    string
	message string
}

// requireDownRefused executes a down file inside a transaction that is always
// rolled back, so the guard is proven without moving the schema version.
func requireDownRefused(t *testing.T, ctx context.Context, db *sql.DB, refusal downRefusal) {
	t.Helper()
	downSQL, err := migrationFiles.ReadFile(refusal.file)
	if err != nil {
		t.Fatalf("read %s: %v", refusal.file, err)
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin guarded down: %v", err)
	}
	_, err = tx.ExecContext(ctx, string(downSQL))
	if err == nil || !strings.Contains(err.Error(), refusal.message) {
		_ = tx.Rollback()
		t.Fatalf("%s error = %v, want refusal containing %q", refusal.file, err, refusal.message)
	}
	_ = tx.Rollback()
}
