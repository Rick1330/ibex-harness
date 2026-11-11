//go:build integration

package billing_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/google/uuid"
)

// TestStore_LoadOrg_AsRuntimeEnforcesHardCap is the positive control for the
// RLS bypass: as its own login, ibex_runtime cannot bypass RLS, so LoadOrg must
// pin ibex_app and set app.current_org_id for the hard-cap row to be visible.
// Before the pin, LoadOrg returned HasHardCap=false and a hard cap stopped
// enforcing with no error.
func TestStore_LoadOrg_AsRuntimeEnforcesHardCap(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	owner := testutil.OpenDB(t, dsn)
	defer func() { _ = owner.Close() }()

	capOrg := seedOrg(t, owner, "Hard Cap")
	noCapOrg := seedOrg(t, owner, "No Cap")
	otherCapOrg := seedOrg(t, owner, "Other Cap")

	wantPeriod := seedHardCapPeriod(t, owner, capOrg, 5000, 250)
	seedHardCapPeriod(t, owner, otherCapOrg, 9999, 1)

	testutil.ProvisionCapabilityLogins(t, dsn)
	runtimeDB := testutil.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	store, err := billing.NewStore(runtimeDB)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}

	got, err := store.LoadOrg(context.Background(), capOrg)
	testutil.RequireNoPermissionDenied(t, err)
	if err != nil {
		t.Fatalf("LoadOrg(capOrg) as ibex_runtime: %v", err)
	}
	if !got.HasHardCap {
		t.Fatal("HasHardCap=false: the hard-cap row was filtered out; RLS is still bypassed or the pin is wrong")
	}
	if got.PeriodID != wantPeriod {
		t.Fatalf("PeriodID=%s want %s", got.PeriodID, wantPeriod)
	}
	if got.CapCents != 5000 || got.SpentCents != 250 {
		t.Fatalf("cap/spent=%d/%d want 5000/250", got.CapCents, got.SpentCents)
	}

	// Negative: an org with no period must not inherit another org's cap.
	none, err := store.LoadOrg(context.Background(), noCapOrg)
	testutil.RequireNoPermissionDenied(t, err)
	if err != nil {
		t.Fatalf("LoadOrg(noCapOrg) as ibex_runtime: %v", err)
	}
	if none.HasHardCap {
		t.Fatalf("noCapOrg saw a hard cap: %+v", none)
	}
}

func seedOrg(t *testing.T, db *sql.DB, name string) uuid.UUID {
	t.Helper()
	slug := "billing-" + uuid.NewString()[:8]
	return uuid.MustParse(testutil.SeedOrganization(t, db, name, slug))
}

func seedHardCapPeriod(t *testing.T, db *sql.DB, orgID uuid.UUID, capCents, spentCents int64) uuid.UUID {
	t.Helper()
	ctx := context.Background()
	now := time.Now().UTC()
	var id uuid.UUID
	err := testutil.WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_billing.budget_periods
				(org_id, period_start, period_end, cap_cents, spent_cents_cached, enforcement_mode)
			VALUES ($1::uuid, $2, $3, $4, $5, 'hard_cap')
			RETURNING id`, orgID, now.Add(-time.Hour), now.Add(time.Hour), capCents, spentCents).Scan(&id)
	})
	if err != nil {
		t.Fatalf("seed hard-cap period: %v", err)
	}
	return id
}
