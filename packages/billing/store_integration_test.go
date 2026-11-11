//go:build integration

package billing_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/google/uuid"
)

// TestStore_LoadOrg_AsRuntimeEnforcesHardCap is the positive control for the
// RLS bypass: as its own login, ibex_runtime cannot bypass RLS, so LoadOrg must
// pin ibex_app and set app.current_org_id for the hard-cap row to be visible.
// Before the pin, LoadOrg returned HasHardCap=false and a hard cap stopped
// enforcing with no error.
func TestStore_LoadOrg_AsRuntimeEnforcesHardCap(t *testing.T) {
	dsn := runtimeconn.DSN()
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}

	owner := runtimeconn.OpenDB(t, dsn)
	defer func() { _ = owner.Close() }()

	capOrg := seedOrg(t, owner, "Hard Cap")
	noCapOrg := seedOrg(t, owner, "No Cap")
	otherCapOrg := seedOrg(t, owner, "Other Cap")

	want := hardCapSeed{org: capOrg, capCents: 5000, spentCents: 250}
	wantPeriod := seedHardCapPeriod(t, owner, want)
	seedHardCapPeriod(t, owner, hardCapSeed{org: otherCapOrg, capCents: 9999, spentCents: 1})

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	store := newStore(t, runtimeDB)
	assertHardCap(t, loadOrg(t, store, "capOrg", capOrg), wantPeriod, want)
	assertNoHardCap(t, loadOrg(t, store, "noCapOrg", noCapOrg))
}

type hardCapSeed struct {
	org        uuid.UUID
	capCents   int64
	spentCents int64
}

func newStore(t *testing.T, db *sql.DB) *billing.Store {
	t.Helper()
	store, err := billing.NewStore(db)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}
	return store
}

func loadOrg(t *testing.T, store *billing.Store, label string, orgID uuid.UUID) billing.BudgetSnapshot {
	t.Helper()
	got, err := store.LoadOrg(context.Background(), orgID)
	runtimeconn.RequireNoPermissionDenied(t, err, "LoadOrg("+label+")")
	if err != nil {
		t.Fatalf("LoadOrg(%s) as ibex_runtime: %v", label, err)
	}
	return got
}

func assertHardCap(t *testing.T, got billing.BudgetSnapshot, periodID uuid.UUID, want hardCapSeed) {
	t.Helper()
	if !got.HasHardCap {
		t.Fatal("HasHardCap=false: the hard-cap row was filtered out; RLS is still bypassed or the pin is wrong")
	}
	if got.PeriodID != periodID {
		t.Fatalf("PeriodID=%s want %s", got.PeriodID, periodID)
	}
	if got.CapCents != want.capCents || got.SpentCents != want.spentCents {
		t.Fatalf("cap/spent=%d/%d want %d/%d", got.CapCents, got.SpentCents, want.capCents, want.spentCents)
	}
}

func assertNoHardCap(t *testing.T, got billing.BudgetSnapshot) {
	t.Helper()
	if got.HasHardCap {
		t.Fatalf("no-cap org saw a hard cap: %+v", got)
	}
}

func seedOrg(t *testing.T, db *sql.DB, name string) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	slug := "billing-" + uuid.NewString()[:8]
	var id string
	err := runtimeconn.WithOwnerTx(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		return tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id::text`,
			name, slug).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed organization: %v", err)
	}
	return uuid.MustParse(id)
}

func seedHardCapPeriod(t *testing.T, db *sql.DB, seed hardCapSeed) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	now := time.Now().UTC()
	var id uuid.UUID
	err := runtimeconn.WithOwnerTx(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_billing.budget_periods
				(org_id, period_start, period_end, cap_cents, spent_cents_cached, enforcement_mode)
			VALUES ($1::uuid, $2, $3, $4, $5, 'hard_cap')
			RETURNING id`, seed.org, now.Add(-time.Hour), now.Add(time.Hour), seed.capCents, seed.spentCents).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed hard-cap period: %v", err)
	}
	return id
}
