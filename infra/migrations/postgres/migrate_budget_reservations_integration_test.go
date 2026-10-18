//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"

	"github.com/lib/pq"
)

// budgetReservationsFixture seeds two orgs with agents plus one active
// hard_cap budget period per org for the budget-reservation schema tests.
type budgetReservationsFixture struct {
	ctx              context.Context
	db               *sql.DB
	orgA, orgB       string
	agentA, agentB   string
	periodA, periodB string
}

func openBudgetReservationsFixture(t *testing.T) budgetReservationsFixture {
	t.Helper()
	ctx, db := setupBillingDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	return budgetReservationsFixture{
		ctx: ctx, db: db,
		orgA: orgA, orgB: orgB,
		agentA:  lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"}),
		agentB:  lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgB, slug: "agent-b"}),
		periodA: billingInsert{t: t, db: db, orgID: orgA}.budgetPeriod(ctx, 10_000),
		periodB: billingInsert{t: t, db: db, orgID: orgB}.budgetPeriod(ctx, 10_000),
	}
}

func (f budgetReservationsFixture) insertClaimedBudgetReservation(t *testing.T, orgID, agentID, periodID, key string) {
	t.Helper()
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, `
			INSERT INTO ibex_core.budget_reservations
				(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
				 state, amount_estimated_cents, lease_expires_at)
			VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 'claimed', 25,
				NOW() + interval '5 minutes')`,
			orgID, agentID, periodID, key, strings.Repeat("a", 64))
		return err
	})
	if err != nil {
		t.Fatalf("insert budget reservation: %v", err)
	}
}

func TestBudgetReservations_SchemaAndRLSCrossTenant(t *testing.T) {
	f := openBudgetReservationsFixture(t)
	assertCoreTableExists(t, f.ctx, f.db, "budget_reservations")
	assertCoreTableRLS(t, f.ctx, coreTableRLSCheck{
		db: f.db, table: "budget_reservations", expect: coreTableRLSFlags{enabled: true, forced: true},
	})

	f.insertClaimedBudgetReservation(t, f.orgA, f.agentA, f.periodA, "key-a")
	f.insertClaimedBudgetReservation(t, f.orgB, f.agentB, f.periodB, "key-b")

	// ibex_app sees only its own org (fail closed with no org context).
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "budget_reservations", orgID: "", want: 0})
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "budget_reservations", orgID: f.orgA, want: 1})
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "budget_reservations", orgID: f.orgB, want: 1})
}

// budgetConstraintCase carries a complete insert statement whose literals
// exercise one schema constraint; ids are bound arguments.
type budgetConstraintCase struct {
	name, values string
	key          string
	code         string
}

func TestBudgetReservations_CheckConstraints(t *testing.T) {
	f := openBudgetReservationsFixture(t)
	hash := strings.Repeat("b", 64)

	cases := []budgetConstraintCase{
		{
			name:   "unknown state",
			values: `'pending', 10, NULL, NULL, NOW() + interval '5 minutes'`,
			code:   "23514",
		},
		{
			name:   "claimed without lease",
			values: `'claimed', 10, NULL, NULL, NULL`,
			code:   "23514",
		},
		{
			name:   "finalized without final amount and completeness",
			values: `'finalized', 10, NULL, NULL, NULL`,
			code:   "23514",
		},
		{
			name:   "finalized with unknown completeness",
			values: `'finalized', 10, 5, 'guessed', NULL`,
			code:   "23514",
		},
		{
			name:   "released with final amounts",
			values: `'released', 10, 5, 'complete', NULL`,
			code:   "23514",
		},
		{
			name:   "released with lease",
			values: `'released', 10, NULL, NULL, NOW() + interval '5 minutes'`,
			code:   "23514",
		},
		{
			name:   "negative estimate",
			values: `'claimed', -1, NULL, NULL, NOW() + interval '5 minutes'`,
			code:   "23514",
		},
		{
			name:   "lease before created_at",
			values: `'claimed', 10, NULL, NULL, NOW() - interval '1 minute'`,
			code:   "23514",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
				_, e := tx.ExecContext(f.ctx, `
					INSERT INTO ibex_core.budget_reservations
						(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
						 state, amount_estimated_cents, amount_final_cents, finalized_completeness, lease_expires_at)
					VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, `+tc.values+`)`,
					f.orgA, f.agentA, f.periodA, "constraint-"+tc.name, hash)
				return e
			})
			requireBudgetSQLState(t, err, tc.code)
		})
	}

	t.Run("malformed request hash", func(t *testing.T) {
		err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
			_, e := tx.ExecContext(f.ctx, `
				INSERT INTO ibex_core.budget_reservations
					(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
					 state, amount_estimated_cents, lease_expires_at)
				VALUES ($1::uuid, $2::uuid, $3::uuid, 'bad-hash', 'zz', 'claimed', 10,
					NOW() + interval '5 minutes')`, f.orgA, f.agentA, f.periodA)
			return e
		})
		requireBudgetSQLState(t, err, "23514")
	})

	t.Run("overlong reservation key", func(t *testing.T) {
		err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
			_, e := tx.ExecContext(f.ctx, `
				INSERT INTO ibex_core.budget_reservations
					(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
					 state, amount_estimated_cents, lease_expires_at)
				VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 'claimed', 10,
					NOW() + interval '5 minutes')`,
				f.orgA, f.agentA, f.periodA, strings.Repeat("k", 257), hash)
			return e
		})
		requireBudgetSQLState(t, err, "23514")
	})

	t.Run("unknown budget period", func(t *testing.T) {
		err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
			_, e := tx.ExecContext(f.ctx, `
				INSERT INTO ibex_core.budget_reservations
					(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
					 state, amount_estimated_cents, lease_expires_at)
				VALUES ($1::uuid, $2::uuid, $3::uuid, 'unknown-period', $4, 'claimed', 10,
					NOW() + interval '5 minutes')`,
				f.orgA, f.agentA, "00000000-0000-0000-0000-000000000000", hash)
			return e
		})
		requireBudgetSQLState(t, err, "23503")
	})

	t.Run("duplicate org agent key", func(t *testing.T) {
		f.insertClaimedBudgetReservation(t, f.orgA, f.agentA, f.periodA, "duplicate-key")
		err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
			_, e := tx.ExecContext(f.ctx, `
				INSERT INTO ibex_core.budget_reservations
					(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
					 state, amount_estimated_cents, lease_expires_at)
				VALUES ($1::uuid, $2::uuid, $3::uuid, 'duplicate-key', $4, 'claimed', 10,
					NOW() + interval '5 minutes')`, f.orgA, f.agentA, f.periodA, hash)
			return e
		})
		requireBudgetSQLState(t, err, "23505")
	})
}

func TestBudgetReservations_MigrationDown(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	if err := Down(dsn); err != nil {
		t.Fatalf("down: %v", err)
	}
	ctx := context.Background()
	var exists bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.tables
			WHERE table_schema = 'ibex_core' AND table_name = 'budget_reservations'
		)`).Scan(&exists)
	if err != nil {
		t.Fatalf("check table: %v", err)
	}
	if exists {
		t.Fatal("budget_reservations still exists after rollback")
	}
}

func requireBudgetSQLState(t *testing.T, err error, code string) {
	t.Helper()
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || string(pqErr.Code) != code {
		t.Fatalf("want sqlstate %s, got %v", code, err)
	}
}
