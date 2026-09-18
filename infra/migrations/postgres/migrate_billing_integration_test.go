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
	cardID := insertRateCard(t, ctx, db, orgA, "default")
	insertRateCardVersion(t, ctx, db, orgA, cardID, 1)
	periodID := insertBudgetPeriod(t, ctx, db, orgA, 10_000)

	assertBillingVisibleToOrg(t, ctx, db, orgA, cardID, periodID)
	assertBillingHiddenFromOrg(t, ctx, db, orgB, orgA)
	assertVersionsImmutable(t, ctx, db, orgA, cardID)
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

func insertRateCard(t *testing.T, ctx context.Context, db *sql.DB, orgID, name string) string {
	t.Helper()
	var id string
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_billing.rate_cards (org_id, name, currency, status)
			VALUES ($1::uuid, $2, 'USD', 'published')
			RETURNING id::text`, orgID, name).Scan(&id)
	})
	if err != nil {
		t.Fatalf("insert rate card: %v", err)
	}
	return id
}

func insertRateCardVersion(t *testing.T, ctx context.Context, db *sql.DB, orgID, cardID string, version int64) {
	t.Helper()
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			INSERT INTO ibex_billing.rate_card_versions (rate_card_id, org_id, version, prices)
			VALUES ($1::uuid, $2::uuid, $3, $4::jsonb)`,
			cardID, orgID, version,
			`[{"provider":"openai","model_pattern":"gpt-4o*","input_cents_per_1k":250,"output_cents_per_1k":1000}]`)
		return e
	})
	if err != nil {
		t.Fatalf("insert rate card version: %v", err)
	}
}

func insertBudgetPeriod(t *testing.T, ctx context.Context, db *sql.DB, orgID string, capCents int64) string {
	t.Helper()
	var id string
	start := time.Now().UTC().Truncate(time.Hour)
	end := start.Add(24 * time.Hour)
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_billing.budget_periods
				(org_id, period_start, period_end, cap_cents, spent_cents_cached, enforcement_mode)
			VALUES ($1::uuid, $2, $3, $4, 0, 'hard_cap')
			RETURNING id::text`, orgID, start, end, capCents).Scan(&id)
	})
	if err != nil {
		t.Fatalf("insert budget period: %v", err)
	}
	return id
}

func insertEnforcementDecision(t *testing.T, ctx context.Context, db *sql.DB, orgID, periodID string) string {
	t.Helper()
	var id string
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_billing.enforcement_decisions
				(org_id, budget_period_id, decision, reason)
			VALUES ($1::uuid, $2::uuid, 'deny', 'cap')
			RETURNING id::text`, orgID, periodID).Scan(&id)
	})
	if err != nil {
		t.Fatalf("insert decision: %v", err)
	}
	return id
}

func countInOrgTx(tx *sql.Tx, ctx context.Context, query string, arg string) (int, error) {
	var n int
	err := tx.QueryRowContext(ctx, query, arg).Scan(&n)
	return n, err
}

func assertBillingVisibleToOrg(t *testing.T, ctx context.Context, db *sql.DB, orgID, cardID, periodID string) {
	t.Helper()
	checks := []struct {
		query string
		arg   string
		label string
	}{
		{`SELECT COUNT(*) FROM ibex_billing.rate_cards WHERE id = $1::uuid`, cardID, "rate_cards"},
		{`SELECT COUNT(*) FROM ibex_billing.rate_card_versions WHERE rate_card_id = $1::uuid`, cardID, "rate_card_versions"},
		{`SELECT COUNT(*) FROM ibex_billing.budget_periods WHERE id = $1::uuid`, periodID, "budget_periods"},
	}
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		for _, c := range checks {
			n, e := countInOrgTx(tx, ctx, c.query, c.arg)
			if e != nil {
				return e
			}
			if n != 1 {
				return fmt.Errorf("%s count=%d", c.label, n)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("org visibility: %v", err)
	}
}

func assertBillingHiddenFromOrg(t *testing.T, ctx context.Context, db *sql.DB, viewerOrg, ownerOrg string) {
	t.Helper()
	tables := []string{
		"ibex_billing.rate_cards",
		"ibex_billing.budget_periods",
		"ibex_billing.rate_card_versions",
	}
	err := withOrgContext(ctx, db, viewerOrg, func(tx *sql.Tx) error {
		for _, table := range tables {
			n, e := countInOrgTx(tx, ctx,
				fmt.Sprintf(`SELECT COUNT(*) FROM %s WHERE org_id = $1::uuid`, table), ownerOrg)
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
		t.Fatalf("cross-tenant RLS: %v", err)
	}
}

func assertVersionsImmutable(t *testing.T, ctx context.Context, db *sql.DB, orgID, cardID string) {
	t.Helper()
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		_, e := tx.ExecContext(ctx, `
			UPDATE ibex_billing.rate_card_versions SET prices = '[]'::jsonb
			WHERE rate_card_id = $1::uuid`, cardID)
		return e
	})
	if err == nil {
		t.Fatal("expected UPDATE on rate_card_versions to fail (no UPDATE grant)")
	}
}

func TestBilling_CompositeFKRejectsCrossOrgParents(t *testing.T) {
	ctx, db := setupBillingDB(t)
	orgA, orgB := seedBillingOrgs(t, ctx, db)
	cardA := insertRateCard(t, ctx, db, orgA, "card-a")
	periodA := insertBudgetPeriod(t, ctx, db, orgA, 5000)

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
	periodID := insertBudgetPeriod(t, ctx, db, orgA, 5000)
	decisionID := insertEnforcementDecision(t, ctx, db, orgA, periodID)

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
	periodID := insertBudgetPeriod(t, ctx, db, orgA, 5000)
	decisionID := insertEnforcementDecision(t, ctx, db, orgA, periodID)

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
