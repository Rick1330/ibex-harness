//go:build integration

package ratelimit_test

import (
	"context"
	"database/sql"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/google/uuid"
)

// TestConfigStore_LoadAll_AsRuntimeReturnsOverrides is the positive control for
// the full override poll. ibex_runtime cannot read rate_limit_overrides across
// tenants directly, so LoadAll must go through the
// ibex_core.rate_limit_overrides_snapshot definer. Before the fix the poll
// returned an empty map and every per-org override was silently ignored.
func TestConfigStore_LoadAll_AsRuntimeReturnsOverrides(t *testing.T) {
	dsn, cleanup := testutil.SetupPostgres(t)
	defer cleanup()

	owner := testutil.OpenDB(t, dsn)
	defer func() { _ = owner.Close() }()

	orgA, agentA := seedOrgAgent(t, owner, "Rate Limit A")
	orgB, _ := seedOrgAgent(t, owner, "Rate Limit B")

	seedOverride(t, owner, orgA, "", 111)
	seedOverride(t, owner, orgA, agentA.String(), 222)
	seedOverride(t, owner, orgB, "", 333)

	testutil.ProvisionCapabilityLogins(t, dsn)
	runtimeDB := testutil.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	store, err := ratelimit.NewConfigStore(runtimeDB)
	if err != nil {
		t.Fatalf("NewConfigStore: %v", err)
	}

	all, err := store.LoadAll(context.Background())
	testutil.RequireNoPermissionDenied(t, err)
	if err != nil {
		t.Fatalf("LoadAll as ibex_runtime: %v", err)
	}

	// Positive: both the org-level and agent-level rows for org A are visible.
	requireRPM(t, all, orgA, nil, 111)
	requireRPM(t, all, orgA, &agentA, 222)

	// Cross-tenant reach is the contract of LoadAll, but each row must stay
	// under its own org: org A must not absorb org B's 333.
	requireRPM(t, all, orgB, nil, 333)
	if got := all[orgA]; got.OrgRPM == nil || *got.OrgRPM != 111 {
		t.Fatalf("org A org-level RPM=%v; org B's value bled into org A", got.OrgRPM)
	}
}

func requireRPM(t *testing.T, all map[uuid.UUID]ratelimit.OrgOverrideSet, orgID uuid.UUID, agentID *uuid.UUID, want int64) {
	t.Helper()
	set, ok := all[orgID]
	if !ok {
		t.Fatalf("org %s missing from LoadAll result", orgID)
	}
	if agentID == nil {
		if set.OrgRPM == nil || *set.OrgRPM != want {
			t.Fatalf("org %s org-level RPM=%v want %d", orgID, set.OrgRPM, want)
		}
		return
	}
	got, ok := set.AgentRPM[*agentID]
	if !ok || got != want {
		t.Fatalf("org %s agent %s RPM=%d/%v want %d", orgID, *agentID, got, ok, want)
	}
}

func seedOrgAgent(t *testing.T, db *sql.DB, name string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	slug := "ratelimit-" + uuid.NewString()[:8]
	orgID := testutil.SeedOrganization(t, db, name, slug)
	userID := testutil.SeedUser(t, db, orgID, slug+"@example.com", name)
	agentID := testutil.SeedAgent(t, db, orgID, userID, name+" Agent", "agent-"+slug)
	return uuid.MustParse(orgID), uuid.MustParse(agentID)
}

func seedOverride(t *testing.T, db *sql.DB, orgID uuid.UUID, agentID string, rpm int64) {
	t.Helper()
	ctx := context.Background()
	var agentArg any
	if agentID != "" {
		agentArg = agentID
	}
	err := testutil.WithServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
			VALUES ($1::uuid, $2::uuid, $3)`, orgID, agentArg, rpm)
		return err
	})
	if err != nil {
		t.Fatalf("seed rate-limit override: %v", err)
	}
}
