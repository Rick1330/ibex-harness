//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

// 000074 adds the erasure state the memory-lifecycle consumer needs
// (erasure_state, erasure_deadline) and the grants that consumer requires: a
// column-scoped UPDATE on the outbox it leases, and a column SELECT on
// session_events.id for ibex_purge, the role that already holds DELETE there. It
// deliberately does NOT grant DELETE on session_events to ibex_app: that table is
// the append-only audit trail, and the request-path identity must not be able to
// erase it without a forget, a receipt and a legal-hold check. It also widens the
// erasure_store_receipts store domain so that copy can be proven like the others.
//
// Forward-only in production (ADR-0098). The down file exists for dev rollback
// and must refuse once a row records erasure progress, because dropping the
// columns turns "attempted and unproven" back into "never ran".
const memoryLifecycleErasureStateVersion = 74

// outboxErasureColumns are the two columns this migration owns on the outbox.
var outboxErasureColumns = []string{"erasure_state", "erasure_deadline"}

// TestMemoryLifecycleErasureState_UpDownUp drives the reversible range end to
// end: migrate to head, roll 000074 back with no progress recorded, and migrate
// up again. The rollback has to be proven here rather than in production.
func TestMemoryLifecycleErasureState_UpDownUp(t *testing.T) {
	f := newMigrationFixture(t, memoryLifecycleErasureStateVersion)

	requireOutboxErasureColumns(t, f.ctx, f.db, true)
	requireSessionEventReceiptAccepted(t, f.ctx, f.db, true)

	downToVersion(t, f.dsn, memoryLifecycleErasureStateVersion-1)
	requireVersion(t, f.dsn, memoryLifecycleErasureStateVersion-1)
	requireOutboxErasureColumns(t, f.ctx, f.db, false)
	requireSessionEventReceiptAccepted(t, f.ctx, f.db, false)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up after clean down: %v", err)
	}
	requireVersion(t, f.dsn, f.head)
	requireOutboxErasureColumns(t, f.ctx, f.db, true)
	requireSessionEventReceiptAccepted(t, f.ctx, f.db, true)
}

// TestMemoryLifecycleErasureState_DownRefusesAfterProgress pins both guards in
// the down file. Each down execution runs inside a transaction that is rolled
// back, so the refusal is proven without leaving the schema below head.
//
// The two guards are proven in separate tests because the first one is global
// over the outbox: once any row records progress, the session_event guard is
// unreachable and a single test would only ever exercise the first refusal.
func TestMemoryLifecycleErasureState_DownRefusesAfterProgress(t *testing.T) {
	f := newMigrationFixture(t, memoryLifecycleErasureStateVersion)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertOutboxRow(t, f.ctx, f.db, outboxSeed{
		orgID: orgA, memoryID: uuid.NewString(), revision: 2, erasureState: "partial",
	})
	requireDownRefused(t, f.ctx, f.db, downRefusal{
		file:    "000074_memory_lifecycle_erasure_state.down.sql",
		message: "refusing destructive 000074 rollback after memory lifecycle erasure state exists",
	})
	requireVersion(t, f.dsn, f.head)
}

// TestMemoryLifecycleErasureState_DownRefusesAfterSessionEventReceipt is the
// second guard on its own: a session_event receipt is evidence the narrowed
// domain cannot hold, and deleting it to make the rollback succeed would delete
// the proof that the store was cleared.
func TestMemoryLifecycleErasureState_DownRefusesAfterSessionEventReceipt(t *testing.T) {
	f := newMigrationFixture(t, memoryLifecycleErasureStateVersion)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertErasureReceipt(t, f.ctx, f.db, erasureReceiptSeed{
		orgID: orgA, memoryID: uuid.NewString(), revision: 2, store: "session_event",
	})
	requireDownRefused(t, f.ctx, f.db, downRefusal{
		file:    "000074_memory_lifecycle_erasure_state.down.sql",
		message: "refusing destructive 000074 rollback after session_event erasure receipts exist",
	})
	requireVersion(t, f.dsn, f.head)
}

// TestMemoryLifecycleErasureState_ConsumerContract asserts the properties the
// consumer relies on: a default state, a closed domain, the session_event
// receipt, and the two grants — including that the new DELETE on session_events
// reaches the caller's own tenant only.
func TestMemoryLifecycleErasureState_ConsumerContract(t *testing.T) {
	f := newMigrationFixture(t, memoryLifecycleErasureStateVersion)

	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	tenants := tenantPair{orgA: orgA, orgB: orgB}
	requireOutboxDefaultState(t, f.ctx, f.db, orgA)
	requireOutboxRejectsUnknownState(t, f.ctx, f.db, orgA)
	requireAppCanLeaseOutbox(t, f.ctx, f.db, orgA)
	requireAppCannotForgeOutboxIdentity(t, f.ctx, f.db, orgA)
	requireAppCannotDeleteSessionEvents(t, f.ctx, f.db, orgA)
	requirePurgeDeletesOwnTenantEventOnly(t, f.ctx, f.db, tenants)
	requireClaimIsCrossTenantAndNarrow(t, f.ctx, f.db, tenants)
	requireClaimRejectsOversizedBudget(t, f.ctx, f.db)
	requireAppCannotClaim(t, f.ctx, f.db)
}

// eventCountCheck is one session_events row and the count it must have.
type eventCountCheck struct {
	eventID int64
	want    int
}

func requireOutboxErasureColumns(t *testing.T, ctx context.Context, db *sql.DB, want bool) {
	t.Helper()
	for _, column := range outboxErasureColumns {
		var present bool
		err := db.QueryRowContext(ctx, `
			SELECT EXISTS (
				SELECT 1 FROM information_schema.columns
				WHERE table_schema = 'ibex_core'
				  AND table_name = 'memory_lifecycle_outbox'
				  AND column_name = $1
			)`, column).Scan(&present)
		if err != nil {
			t.Fatalf("check column %s: %v", column, err)
		}
		if present != want {
			t.Fatalf("ibex_core.memory_lifecycle_outbox.%s present = %v, want %v",
				column, present, want)
		}
	}
}

// requireSessionEventReceiptAccepted proves the widened store domain is in force
// (and gone after rollback) by inserting one receipt of that store. The insert
// runs in a transaction that is always rolled back: a committed row would trip
// the down guard in the same test and prove nothing about the rollback.
func requireSessionEventReceiptAccepted(t *testing.T, ctx context.Context, db *sql.DB, want bool) {
	t.Helper()
	orgID := seedOrgForStoreDomain(t, ctx, db)
	err := withRolledBackServiceAccount(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli - literal statement with $N bind parameters; nothing is concatenated into the SQL.
		_, execErr := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.erasure_store_receipts
				(org_id, memory_id, revision, store, status, idempotency_key)
			VALUES ($1::uuid, $2::uuid, 1, 'session_event', 'verified', $3)`,
			orgID, uuid.NewString(), "domain-"+orgID)
		return execErr
	})
	if want {
		if err != nil {
			t.Fatalf("session_event receipt rejected: %v", err)
		}
		return
	}
	requireSQLState(t, err, "23514", "session_event receipt")
}

// withRolledBackServiceAccount runs fn in a service-account transaction and
// always rolls back, so a probe row never survives into the next assertion.
func withRolledBackServiceAccount(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return err
	}
	return fn(tx)
}

// requireSQLState fails the test unless err is a PostgreSQL error with code.
func requireSQLState(t *testing.T, err error, code, what string) *pq.Error {
	t.Helper()
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		t.Fatalf("%s error = %v, want SQLSTATE %s", what, err, code)
	}
	if string(pqErr.Code) != code {
		t.Fatalf("%s error = %v, want SQLSTATE %s", what, err, code)
	}
	return pqErr
}

func seedOrgForStoreDomain(t *testing.T, ctx context.Context, db *sql.DB) string {
	t.Helper()
	var orgID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var err error
		orgID, err = insertOrg(ctx, tx, "Store domain org", "store-domain-"+uuid.NewString()[:8])
		return err
	})
	if err != nil {
		t.Fatalf("seed org: %v", err)
	}
	return orgID
}

// insertOutboxRowWithoutState seeds a row that does not name erasure_state, the
// way the existing forget path writes it, and returns its memory id.
func insertOutboxRowWithoutState(t *testing.T, ctx context.Context, db *sql.DB, orgID string) string {
	t.Helper()
	memoryID := uuid.NewString()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx,
			`INSERT INTO ibex_core.memory_lifecycle_outbox
				(org_id, memory_id, revision, event_type)
			VALUES ($1::uuid, $2::uuid, 2, 'forgotten')`, orgID, memoryID)
		return execErr
	})
	if err != nil {
		t.Fatalf("insert default outbox row: %v", err)
	}
	return memoryID
}

// requireOutboxDefaultState pins that a row written by the existing forget path,
// which does not name the column, is pending rather than NULL or complete.
func requireOutboxDefaultState(t *testing.T, ctx context.Context, db *sql.DB, orgID string) {
	t.Helper()
	memoryID := insertOutboxRowWithoutState(t, ctx, db, orgID)
	var state string
	var deadline sql.NullTime
	err := db.QueryRowContext(ctx, `
		SELECT erasure_state, erasure_deadline FROM ibex_core.memory_lifecycle_outbox
		WHERE memory_id = $1::uuid`, memoryID).Scan(&state, &deadline)
	if err != nil {
		t.Fatalf("read default state: %v", err)
	}
	if state != "pending" {
		t.Fatalf("default erasure_state = %q, want pending", state)
	}
	if deadline.Valid {
		t.Fatalf("erasure_deadline = %v, want NULL before the first claim", deadline.Time)
	}
}

func requireOutboxRejectsUnknownState(t *testing.T, ctx context.Context, db *sql.DB, orgID string) {
	t.Helper()
	seed := outboxSeed{
		orgID: orgID, memoryID: uuid.NewString(), revision: 3, erasureState: "erased",
	}
	requireSQLState(t, insertOutboxWithState(ctx, db, seed), "23514", "unknown erasure_state")
}

// requireAppCanLeaseOutbox is the grant that makes the consumer possible: as
// ibex_app with the org GUC it must be able to claim (attempts, locked_until) and
// settle (erasure_state, delivered_at) its own tenant's row, and nothing else.
func requireAppCanLeaseOutbox(t *testing.T, ctx context.Context, db *sql.DB, orgID string) {
	t.Helper()
	memoryID := seedPendingOutboxRow(t, ctx, db, orgID)
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		result, execErr := tx.ExecContext(ctx, `
			UPDATE ibex_core.memory_lifecycle_outbox
			SET attempts = attempts + 1,
			    locked_until = NOW() + interval '900 seconds',
			    erasure_state = 'complete',
			    delivered_at = NOW()
			WHERE memory_id = $1::uuid AND org_id = $2::uuid`, memoryID, orgID)
		if execErr != nil {
			return execErr
		}
		affected, rowsErr := result.RowsAffected()
		if rowsErr != nil {
			return rowsErr
		}
		if affected != 1 {
			t.Fatalf("ibex_app leased %d outbox rows, want 1", affected)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("ibex_app lease: %v", err)
	}
}

// requireAppCannotDeleteSessionEvents is the negative half of the F1 fix: the
// request-path identity must not be able to delete the append-only audit trail at
// all, even for its own tenant. Without the grant the only delete path is
// ibex_purge (and the owner), so an audit row can only be removed by the saga
// that writes a receipt for it.
func requireAppCannotDeleteSessionEvents(t *testing.T, ctx context.Context, db *sql.DB, orgA string) {
	t.Helper()
	eventA := insertSessionEvent(t, ctx, db, orgA)
	err := withOrgContext(ctx, db, orgA, func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx,
			`DELETE FROM ibex_core.session_events WHERE id = $1 AND org_id = $2::uuid`, eventA, orgA)
		return execErr
	})
	requireSQLState(t, err, "42501", "ibex_app DELETE session_events")
	requireSessionEventCount(t, ctx, db, eventCountCheck{eventID: eventA, want: 1})
}

// purgeDelete is one row-targeted DELETE and the row count it must report.
type purgeDelete struct {
	orgID   string
	eventID int64
	want    int64
}

// requirePurgeDeletesOwnTenantEventOnly proves the grant landed on the right
// role: ibex_purge holds DELETE (000064) plus the column SELECT on id that a
// row-targeted DELETE needs, and rls_evidence_visible still fences it to the org
// GUC, so another tenant's event survives.
func requirePurgeDeletesOwnTenantEventOnly(t *testing.T, ctx context.Context, db *sql.DB, tenants tenantPair) {
	t.Helper()
	ownEvent := insertSessionEvent(t, ctx, db, tenants.orgA)
	foreignEvent := insertSessionEvent(t, ctx, db, tenants.orgB)
	err := withOrgRoleContext(ctx, db, "ibex_purge", tenants.orgA, func(tx *sql.Tx) error {
		own := purgeDelete{orgID: tenants.orgA, eventID: ownEvent, want: 1}
		if err := requirePurgeDelete(ctx, tx, own); err != nil {
			return err
		}
		foreign := purgeDelete{orgID: tenants.orgB, eventID: foreignEvent, want: 0}
		return requirePurgeDelete(ctx, tx, foreign)
	})
	if err != nil {
		t.Fatalf("ibex_purge session_events delete: %v", err)
	}
	requireSessionEventCount(t, ctx, db, eventCountCheck{eventID: ownEvent, want: 0})
	requireSessionEventCount(t, ctx, db, eventCountCheck{eventID: foreignEvent, want: 1})
}

// requirePurgeDelete deletes one event as ibex_purge and checks how many rows moved.
func requirePurgeDelete(ctx context.Context, tx *sql.Tx, del purgeDelete) error {
	result, err := tx.ExecContext(ctx,
		`DELETE FROM ibex_core.session_events WHERE id = $1 AND org_id = $2::uuid`,
		del.eventID, del.orgID)
	if err != nil {
		return err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected != del.want {
		return fmt.Errorf("ibex_purge deleted %d rows for org %s, want %d",
			affected, del.orgID, del.want)
	}
	return nil
}

func requireSessionEventCount(t *testing.T, ctx context.Context, db *sql.DB, check eventCountCheck) {
	t.Helper()
	var got int
	if err := db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM ibex_core.session_events WHERE id = $1`, check.eventID).Scan(&got); err != nil {
		t.Fatalf("count session event %d: %v", check.eventID, err)
	}
	if got != check.want {
		t.Fatalf("session event %d count = %d, want %d", check.eventID, got, check.want)
	}
}

// requireAppCannotForgeOutboxIdentity is the negative half of the F2 fix. The
// tenant identity may lease and settle a row (attempts, locked_until,
// erasure_state, available_at, delivered_at) but must not be able to rewrite the
// columns that say what the row *is*: forging erasure_state = 'complete' on a
// live `created` row, or retargeting the row onto another memory, is the
// privilege-escalation path the table-wide UPDATE used to allow.
func requireAppCannotForgeOutboxIdentity(t *testing.T, ctx context.Context, db *sql.DB, orgID string) {
	t.Helper()
	memoryID := seedPendingOutboxRow(t, ctx, db, orgID)
	for _, column := range []struct{ name, assignment string }{
		{"event_type", "event_type = 'forgotten'"},
		{"org_id", "org_id = gen_random_uuid()"},
		{"memory_id", "memory_id = gen_random_uuid()"},
		{"revision", "revision = revision + 1"},
	} {
		err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
			_, execErr := tx.ExecContext(ctx, `
				UPDATE ibex_core.memory_lifecycle_outbox
				   SET `+column.assignment+`
				 WHERE memory_id = $1::uuid AND org_id = $2::uuid`, memoryID, orgID)
			return execErr
		})
		requireSQLState(t, err, "42501", "ibex_app UPDATE ... SET "+column.name)
	}
}

// claimBudgetCase is one claim call that must be refused and the parameter the
// refusal has to name.
type claimBudgetCase struct {
	name, query, message string
}

// oversizedClaimBudgets are the two caps the claim function enforces itself.
var oversizedClaimBudgets = []claimBudgetCase{
	{
		name:    "lease",
		query:   `SELECT * FROM ibex_core.memory_lifecycle_claim_erasure(1, 3601.0, 60.0)`,
		message: "p_lease_seconds",
	},
	{
		name:    "deadline",
		query:   `SELECT * FROM ibex_core.memory_lifecycle_claim_erasure(1, 60.0, 604801.0)`,
		message: "p_deadline_seconds",
	},
}

// claimAtDocumentedMaximum is the call the caps must still accept.
const claimAtDocumentedMaximum = `SELECT * FROM ibex_core.memory_lifecycle_claim_erasure(1, 3600.0, 604800.0)`

// claimErr runs one claim query as ibex_worker and returns its error.
func claimErr(ctx context.Context, db *sql.DB, query string) error {
	return withRoleTx(ctx, db, "ibex_worker", func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx, query)
		return execErr
	})
}

// requireClaimRejectsOversizedBudget pins the function's own bounds. The worker's
// Settings cap the same values, but the function is EXECUTE-able directly by the
// worker login, so the limit has to exist where the lease is written.
func requireClaimRejectsOversizedBudget(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	for _, over := range oversizedClaimBudgets {
		requireClaimRefused(t, ctx, db, over)
	}
	// The caps themselves are inclusive: a caller at the documented maximum is
	// not rejected.
	if err := claimErr(ctx, db, claimAtDocumentedMaximum); err != nil {
		t.Fatalf("claim at the documented maximum rejected: %v", err)
	}
}

// requireClaimRefused proves one over-cap claim fails with the parameter named.
func requireClaimRefused(t *testing.T, ctx context.Context, db *sql.DB, over claimBudgetCase) {
	t.Helper()
	err := claimErr(ctx, db, over.query)
	pqErr := requireSQLState(t, err, "P0001", over.name+" above its cap")
	if !strings.Contains(pqErr.Message, over.message) {
		t.Fatalf("%s refusal named %q, want %q", over.name, pqErr.Message, over.message)
	}
}

// claimRow is one row the SECURITY DEFINER claim returned.
type claimRow struct {
	orgID, memoryID, eventType string
	attempts                   int
	deadline                   sql.NullTime
}

// requireNarrow fails when a claimed row describes a memory that still exists, or
// was not leased the way the consumer expects.
func (r claimRow) requireNarrow(t *testing.T, createdID string) {
	t.Helper()
	if r.eventType == "created" {
		t.Fatalf("claim returned a non-erasure event type %q", r.eventType)
	}
	if r.memoryID == createdID {
		t.Fatal("claim returned the created event")
	}
	if r.attempts != 1 {
		t.Fatalf("claim attempts = %d, want 1", r.attempts)
	}
	if !r.deadline.Valid {
		t.Fatal("claim left erasure_deadline NULL; the deadline is set at first claim")
	}
}

// seedClaimCandidates queues one claimable row per tenant plus a `created` row
// the claim must never return, and returns the created row's memory id.
func seedClaimCandidates(t *testing.T, ctx context.Context, db *sql.DB, tenants tenantPair) string {
	t.Helper()
	insertOutboxRow(t, ctx, db, outboxSeed{
		orgID: tenants.orgA, memoryID: uuid.NewString(), revision: 2, erasureState: "pending",
	})
	insertOutboxRow(t, ctx, db, outboxSeed{
		orgID: tenants.orgB, memoryID: uuid.NewString(), revision: 2, erasureState: "partial",
	})
	createdID := uuid.NewString()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memory_lifecycle_outbox
				(org_id, memory_id, revision, event_type)
			VALUES ($1::uuid, $2::uuid, 2, 'created')`, tenants.orgA, createdID)
		return execErr
	})
	if err != nil {
		t.Fatalf("seed created event: %v", err)
	}
	return createdID
}

// collectClaimedRows records the orgs the claim reached and checks every row.
func collectClaimedRows(t *testing.T, rows *sql.Rows, createdID string, orgs map[string]bool) error {
	for rows.Next() {
		var row claimRow
		if err := rows.Scan(&row.orgID, &row.memoryID, &row.eventType,
			&row.attempts, &row.deadline); err != nil {
			return err
		}
		row.requireNarrow(t, createdID)
		orgs[row.orgID] = true
	}
	return rows.Err()
}

// requireClaimedOrgs runs the claim as ibex_worker and returns the orgs it
// reached, failing the test on any row that is not a narrow lease-holding claim.
func requireClaimedOrgs(t *testing.T, ctx context.Context, db *sql.DB, createdID string) map[string]bool {
	t.Helper()
	orgs := map[string]bool{}
	err := withRoleTx(ctx, db, "ibex_worker", func(tx *sql.Tx) error {
		rows, queryErr := tx.QueryContext(ctx, `
			SELECT org_id::text, memory_id::text, event_type, attempts, erasure_deadline
			  FROM ibex_core.memory_lifecycle_claim_erasure(8, 900.0, 900.0)`)
		if queryErr != nil {
			return queryErr
		}
		defer func() { _ = rows.Close() }()
		return collectClaimedRows(t, rows, createdID, orgs)
	})
	if err != nil {
		t.Fatalf("claim as ibex_worker: %v", err)
	}
	return orgs
}

// requireClaimIsCrossTenantAndNarrow proves the SECURITY DEFINER claim is what
// makes a scheduled sweep possible at all: the outbox is RLS-scoped, so a tenant
// identity sees no row without its own org GUC. As ibex_worker — which holds no
// table grant — the function must return rows for both tenants, and must not
// return an event type that describes a memory that still exists.
func requireClaimIsCrossTenantAndNarrow(t *testing.T, ctx context.Context, db *sql.DB, tenants tenantPair) {
	t.Helper()
	createdID := seedClaimCandidates(t, ctx, db, tenants)
	orgs := requireClaimedOrgs(t, ctx, db, createdID)
	if !orgs[tenants.orgA] || !orgs[tenants.orgB] {
		t.Fatalf("claim reached orgs %v, want both %s and %s", orgs, tenants.orgA, tenants.orgB)
	}
}

// requireAppCannotClaim pins the grant: a tenant identity must not be able to
// lease another tenant's erasure work.
func requireAppCannotClaim(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	var granted bool
	err := db.QueryRowContext(ctx, `
		SELECT has_function_privilege(
			'ibex_app',
			'ibex_core.memory_lifecycle_claim_erasure(integer,double precision,double precision)',
			'EXECUTE')`).Scan(&granted)
	if err != nil {
		t.Fatalf("check ibex_app EXECUTE: %v", err)
	}
	if granted {
		t.Fatal("ibex_app must not be able to execute the cross-tenant claim function")
	}
	err = withRoleTx(ctx, db, "ibex_app", func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx,
			`SELECT * FROM ibex_core.memory_lifecycle_claim_erasure(1, 60.0, 60.0)`)
		return execErr
	})
	requireSQLState(t, err, "42501", "ibex_app claim")
}

// withRoleTx runs fn in a transaction that is pinned to role and always rolled
// back, so a claim's lease never survives into the next assertion.
func withRoleTx(ctx context.Context, db *sql.DB, role string, fn func(*sql.Tx) error) error {
	statement, err := roleStatement(role)
	if err != nil {
		return err
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, statement); err != nil {
		return fmt.Errorf("set role %s: %w", role, err)
	}
	return fn(tx)
}

func insertSessionEvent(t *testing.T, ctx context.Context, db *sql.DB, orgID string) int64 {
	t.Helper()
	var eventID int64
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		// session_events carries a composite FK to sessions (id, org_id), so the
		// capture event needs a real session in the same tenant.
		sessionID := uuid.NewString()
		if _, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.sessions (id, org_id, agent_id, model, provider)
			SELECT $1::uuid, $2::uuid, a.id, 'gpt-4o-mini', 'openai'
			  FROM ibex_core.agents a
			 WHERE a.org_id = $2::uuid
			 LIMIT 1`, sessionID, orgID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.session_events
				(session_id, org_id, sequence_number, event_type, data)
			VALUES ($1::uuid, $2::uuid, 1, 'inference_response', '{}'::jsonb)
			RETURNING id`, sessionID, orgID).Scan(&eventID)
	})
	if err != nil {
		t.Fatalf("insert session event: %v", err)
	}
	return eventID
}
