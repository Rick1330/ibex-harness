//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"testing"
	"time"
)

func TestBilling_SchemaAndRLSCrossTenant(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()

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

func assertBillingVisibleToOrg(t *testing.T, ctx context.Context, db *sql.DB, orgID, cardID, periodID string) {
	t.Helper()
	err := withOrgContext(ctx, db, orgID, func(tx *sql.Tx) error {
		var n int
		if e := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_billing.rate_cards WHERE id = $1::uuid`, cardID).Scan(&n); e != nil {
			return e
		}
		if n != 1 {
			return fmt.Errorf("rate_cards count=%d", n)
		}
		if e := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_billing.rate_card_versions WHERE rate_card_id = $1::uuid`, cardID).Scan(&n); e != nil {
			return e
		}
		if n != 1 {
			return fmt.Errorf("rate_card_versions count=%d", n)
		}
		if e := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_billing.budget_periods WHERE id = $1::uuid`, periodID).Scan(&n); e != nil {
			return e
		}
		if n != 1 {
			return fmt.Errorf("budget_periods count=%d", n)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("org visibility: %v", err)
	}
}

func assertBillingHiddenFromOrg(t *testing.T, ctx context.Context, db *sql.DB, viewerOrg, ownerOrg string) {
	t.Helper()
	err := withOrgContext(ctx, db, viewerOrg, func(tx *sql.Tx) error {
		var n int
		if e := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_billing.rate_cards WHERE org_id = $1::uuid`, ownerOrg).Scan(&n); e != nil {
			return e
		}
		if n != 0 {
			return fmt.Errorf("viewer saw %d rate_cards for owner", n)
		}
		if e := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_billing.budget_periods WHERE org_id = $1::uuid`, ownerOrg).Scan(&n); e != nil {
			return e
		}
		if n != 0 {
			return fmt.Errorf("viewer saw %d budget_periods for owner", n)
		}
		if e := tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_billing.rate_card_versions WHERE org_id = $1::uuid`, ownerOrg).Scan(&n); e != nil {
			return e
		}
		if n != 0 {
			return fmt.Errorf("viewer saw %d rate_card_versions for owner", n)
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
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()
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
