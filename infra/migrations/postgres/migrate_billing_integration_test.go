//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"testing"
	"time"
)

func setupBillingDB(t *testing.T) (context.Context, *sql.DB) {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	t.Cleanup(func() { _ = db.Close() })
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	return context.Background(), db
}

func TestBilling_SchemaAndRLSCrossTenant(t *testing.T) {
	ctx, db := setupBillingDB(t)
	orgA, orgB := seedBillingOrgs(t, ctx, db)

	insA := billingInsert{t: t, ctx: ctx, db: db, orgID: orgA}
	cardID := insA.rateCard("default")
	insA.rateCardVersion(cardID, 1)
	periodID := insA.budgetPeriod(10_000)

	billingAssert{t: t, ctx: ctx, db: db, orgID: orgA}.visible(billingVisibilityIDs{
		cardID: cardID, periodID: periodID,
	})
	billingAssert{t: t, ctx: ctx, db: db, orgID: orgB}.hiddenFrom(orgA)
	billingAssert{t: t, ctx: ctx, db: db, orgID: orgA}.versionsImmutable(cardID)
}

func seedBillingOrgs(t *testing.T, ctx context.Context, db *sql.DB) (orgA, orgB string) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var e error
		orgA, e = insertOrg(ctx, tx, "Billing Org A", "billing-org-a")
		if e != nil {
			return e
		}
		orgB, e = insertOrg(ctx, tx, "Billing Org B", "billing-org-b")
		return e
	})
	if err != nil {
		t.Fatalf("seed orgs: %v", err)
	}
	return orgA, orgB
}

type billingInsert struct {
	t     *testing.T
	ctx   context.Context
	db    *sql.DB
	orgID string
}

func (b billingInsert) returningID(query string, args ...any) string {
	b.t.Helper()
	var id string
	err := withOrgContext(b.ctx, b.db, b.orgID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(b.ctx, query, args...).Scan(&id)
	})
	if err != nil {
		b.t.Fatalf("insert returning id: %v", err)
	}
	return id
}

func (b billingInsert) exec(query string, args ...any) {
	b.t.Helper()
	err := withOrgContext(b.ctx, b.db, b.orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(b.ctx, query, args...)
		return e
	})
	if err != nil {
		b.t.Fatalf("exec: %v", err)
	}
}

func (b billingInsert) rateCard(name string) string {
	b.t.Helper()
	return b.returningID(`
		INSERT INTO ibex_billing.rate_cards (org_id, name, currency, status)
		VALUES ($1::uuid, $2, 'USD', 'published')
		RETURNING id::text`, b.orgID, name)
}

func (b billingInsert) rateCardVersion(cardID string, version int64) {
	b.t.Helper()
	b.exec(`
		INSERT INTO ibex_billing.rate_card_versions (rate_card_id, org_id, version, prices)
		VALUES ($1::uuid, $2::uuid, $3, $4::jsonb)`,
		cardID, b.orgID, version,
		`[{"provider":"openai","model_pattern":"gpt-4o*","input_cents_per_1k":250,"output_cents_per_1k":1000}]`)
}

func (b billingInsert) budgetPeriod(capCents int64) string {
	b.t.Helper()
	start := time.Now().UTC().Truncate(time.Hour)
	end := start.Add(24 * time.Hour)
	return b.returningID(`
		INSERT INTO ibex_billing.budget_periods
			(org_id, period_start, period_end, cap_cents, spent_cents_cached, enforcement_mode)
		VALUES ($1::uuid, $2, $3, $4, 0, 'hard_cap')
		RETURNING id::text`, b.orgID, start, end, capCents)
}

func (b billingInsert) enforcementDecision(periodID string) string {
	b.t.Helper()
	return b.returningID(`
		INSERT INTO ibex_billing.enforcement_decisions
			(org_id, budget_period_id, decision, reason)
		VALUES ($1::uuid, $2::uuid, 'deny', 'cap')
		RETURNING id::text`, b.orgID, periodID)
}

type orgCountQuery struct {
	sql string
	arg string
}

func countInOrgTx(tx *sql.Tx, ctx context.Context, q orgCountQuery) (int, error) {
	var n int
	err := tx.QueryRowContext(ctx, q.sql, q.arg).Scan(&n)
	return n, err
}

type billingAssert struct {
	t     *testing.T
	ctx   context.Context
	db    *sql.DB
	orgID string
}

type billingVisibilityIDs struct {
	cardID   string
	periodID string
}

func (a billingAssert) visible(ids billingVisibilityIDs) {
	a.t.Helper()
	checks := []orgCountQuery{
		{`SELECT COUNT(*) FROM ibex_billing.rate_cards WHERE id = $1::uuid`, ids.cardID},
		{`SELECT COUNT(*) FROM ibex_billing.rate_card_versions WHERE rate_card_id = $1::uuid`, ids.cardID},
		{`SELECT COUNT(*) FROM ibex_billing.budget_periods WHERE id = $1::uuid`, ids.periodID},
	}
	err := withOrgContext(a.ctx, a.db, a.orgID, func(tx *sql.Tx) error {
		for _, c := range checks {
			n, e := countInOrgTx(tx, a.ctx, c)
			if e != nil {
				return e
			}
			if n != 1 {
				return fmt.Errorf("expected 1 row, got %d for %q", n, c.sql)
			}
		}
		return nil
	})
	if err != nil {
		a.t.Fatalf("org visibility: %v", err)
	}
}

func (a billingAssert) hiddenFrom(ownerOrg string) {
	a.t.Helper()
	tables := []string{
		"ibex_billing.rate_cards",
		"ibex_billing.budget_periods",
		"ibex_billing.rate_card_versions",
	}
	err := withOrgContext(a.ctx, a.db, a.orgID, func(tx *sql.Tx) error {
		for _, table := range tables {
			n, e := countInOrgTx(tx, a.ctx, orgCountQuery{
				sql: fmt.Sprintf(`SELECT COUNT(*) FROM %s WHERE org_id = $1::uuid`, table),
				arg: ownerOrg,
			})
			if e != nil {
				return e
			}
			if n != 0 {
				return fmt.Errorf("viewer saw %d rows in %s for owner", n, table)
			}
		}
		return nil
	})
	if err != nil {
		a.t.Fatalf("cross-tenant RLS: %v", err)
	}
}

func (a billingAssert) versionsImmutable(cardID string) {
	a.t.Helper()
	err := withOrgContext(a.ctx, a.db, a.orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(a.ctx, `
			UPDATE ibex_billing.rate_card_versions SET prices = '[]'::jsonb
			WHERE rate_card_id = $1::uuid`, cardID)
		return e
	})
	if err == nil {
		a.t.Fatal("expected UPDATE on rate_card_versions to fail (no UPDATE grant)")
	}
}

func TestBilling_CompositeFKRejectsCrossOrgParents(t *testing.T) {
	ctx, db := setupBillingDB(t)
	orgA, orgB := seedBillingOrgs(t, ctx, db)
	insA := billingInsert{t: t, ctx: ctx, db: db, orgID: orgA}
	cardA := insA.rateCard("card-a")
	periodA := insA.budgetPeriod(5000)

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			INSERT INTO ibex_billing.rate_card_versions (rate_card_id, org_id, version, prices)
			VALUES ($1::uuid, $2::uuid, 1, '[]'::jsonb)`, cardA, orgB)
		return e
	})
	if err == nil {
		t.Fatal("expected cross-org rate_card_versions insert to fail composite FK")
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			INSERT INTO ibex_billing.enforcement_decisions
				(org_id, budget_period_id, decision, reason)
			VALUES ($1::uuid, $2::uuid, 'deny', 'cross-org')`, orgB, periodA)
		return e
	})
	if err == nil {
		t.Fatal("expected cross-org enforcement_decisions insert to fail composite FK")
	}
}

func TestBilling_PeriodDeleteClearsDecisionPeriodIDOnly(t *testing.T) {
	ctx, db := setupBillingDB(t)
	orgA, _ := seedBillingOrgs(t, ctx, db)
	ins := billingInsert{t: t, ctx: ctx, db: db, orgID: orgA}
	periodID := ins.budgetPeriod(5000)
	decisionID := ins.enforcementDecision(periodID)

	err := withOrgContext(ctx, db, orgA, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `DELETE FROM ibex_billing.budget_periods WHERE id = $1::uuid`, periodID)
		return e
	})
	if err != nil {
		t.Fatalf("delete period: %v", err)
	}
	err = withOrgContext(ctx, db, orgA, func(tx *sql.Tx) error {
		var orgID string
		var period sql.NullString
		if e := tx.QueryRowContext(ctx, `
			SELECT org_id::text, budget_period_id::text
			FROM ibex_billing.enforcement_decisions WHERE id = $1::uuid`, decisionID,
		).Scan(&orgID, &period); e != nil {
			return e
		}
		if orgID != orgA {
			return fmt.Errorf("org_id cleared: %s", orgID)
		}
		if period.Valid {
			return fmt.Errorf("budget_period_id still set: %s", period.String)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("decision after period delete: %v", err)
	}
}

func TestBilling_AppCannotDirectUpdateEnforcementPeriodID(t *testing.T) {
	ctx, db := setupBillingDB(t)
	orgA, _ := seedBillingOrgs(t, ctx, db)
	ins := billingInsert{t: t, ctx: ctx, db: db, orgID: orgA}
	periodID := ins.budgetPeriod(5000)
	decisionID := ins.enforcementDecision(periodID)

	err := withOrgContext(ctx, db, orgA, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			UPDATE ibex_billing.enforcement_decisions
			SET budget_period_id = NULL
			WHERE id = $1::uuid`, decisionID)
		return e
	})
	if err == nil {
		t.Fatal("expected direct UPDATE of budget_period_id to be denied")
	}
}
