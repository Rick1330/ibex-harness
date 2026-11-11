//go:build integration

package ratelimit_test

import (
	"context"
	"database/sql"
	"testing"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/google/uuid"
)

// TestConfigStore_LoadOrg_AsRuntimeReturnsOrgOverrides is the positive control
// for the per-org read. ibex_runtime holds no table grant of its own, so the
// read succeeds only because LoadOrg pins ibex_app and the org GUC for its
// transaction. A 42501 here means the pin is missing, not that the org has no
// overrides.
func TestConfigStore_LoadOrg_AsRuntimeReturnsOrgOverrides(t *testing.T) {
	dsn := runtimeconn.DSN()
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}

	owner := runtimeconn.OpenDB(t, dsn)
	defer func() { _ = owner.Close() }()

	a := seedOrgAgent(t, owner, "Rate Limit Org Read")
	b := seedOrgAgent(t, owner, "Rate Limit Org Other")
	seedOverride(t, owner, overrideSeed{orgID: a.org, rpm: 111})
	seedOverride(t, owner, overrideSeed{orgID: a.org, agentID: a.agent.String(), rpm: 222})
	seedOverride(t, owner, overrideSeed{orgID: b.org, rpm: 333})

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	store := newConfigStore(t, runtimeDB)
	set, err := store.LoadOrg(context.Background(), a.org)
	runtimeconn.RequireNoPermissionDenied(t, err, "LoadOrg")
	if err != nil {
		t.Fatalf("LoadOrg as ibex_runtime: %v", err)
	}
	if set.OrgRPM == nil || *set.OrgRPM != 111 {
		t.Fatalf("org-level RPM=%v want 111", set.OrgRPM)
	}
	if got := set.AgentRPM[a.agent]; got != 222 {
		t.Fatalf("agent RPM=%d want 222", got)
	}
	if _, ok := set.AgentRPM[b.agent]; ok {
		t.Fatal("LoadOrg returned another org's agent override")
	}
}

// TestConfigStore_LoadAll_AsRuntimeReturnsOverrides is the positive control for
// the full override poll. ibex_runtime cannot read rate_limit_overrides across
// tenants directly, so LoadAll must go through the
// ibex_core.rate_limit_overrides_snapshot definer. Before the fix the poll
// returned an empty map and every per-org override was silently ignored.
func TestConfigStore_LoadAll_AsRuntimeReturnsOverrides(t *testing.T) {
	dsn := runtimeconn.DSN()
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}

	owner := runtimeconn.OpenDB(t, dsn)
	defer func() { _ = owner.Close() }()

	a := seedOrgAgent(t, owner, "Rate Limit A")
	b := seedOrgAgent(t, owner, "Rate Limit B")
	seedOverride(t, owner, overrideSeed{orgID: a.org, rpm: 111})
	seedOverride(t, owner, overrideSeed{orgID: a.org, agentID: a.agent.String(), rpm: 222})
	seedOverride(t, owner, overrideSeed{orgID: b.org, rpm: 333})

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	all := loadAll(t, newConfigStore(t, runtimeDB))
	requireRPM(t, all, rpmWant{orgID: a.org, want: 111})
	requireRPM(t, all, rpmWant{orgID: a.org, agentID: &a.agent, want: 222})
	requireRPM(t, all, rpmWant{orgID: b.org, want: 333})
	requireNoBleed(t, all, a.org, 111)
}

type orgAgent struct {
	org   uuid.UUID
	agent uuid.UUID
}

type overrideSeed struct {
	orgID   uuid.UUID
	agentID string
	rpm     int64
}

type rpmWant struct {
	orgID   uuid.UUID
	agentID *uuid.UUID
	want    int64
}

func newConfigStore(t *testing.T, db *sql.DB) *ratelimit.ConfigStore {
	t.Helper()
	store, err := ratelimit.NewConfigStore(db)
	if err != nil {
		t.Fatalf("NewConfigStore: %v", err)
	}
	return store
}

func loadAll(t *testing.T, store *ratelimit.ConfigStore) map[uuid.UUID]ratelimit.OrgOverrideSet {
	t.Helper()
	all, err := store.LoadAll(context.Background())
	runtimeconn.RequireNoPermissionDenied(t, err, "LoadAll")
	if err != nil {
		t.Fatalf("LoadAll as ibex_runtime: %v", err)
	}
	return all
}

func requireRPM(t *testing.T, all map[uuid.UUID]ratelimit.OrgOverrideSet, want rpmWant) {
	t.Helper()
	set, ok := all[want.orgID]
	if !ok {
		t.Fatalf("org %s missing from LoadAll result", want.orgID)
	}
	if want.agentID == nil {
		requireOrgRPM(t, want.orgID, set, want.want)
		return
	}
	got, ok := set.AgentRPM[*want.agentID]
	if !ok || got != want.want {
		t.Fatalf("org %s agent %s RPM=%d/%v want %d", want.orgID, *want.agentID, got, ok, want.want)
	}
}

func requireOrgRPM(t *testing.T, orgID uuid.UUID, set ratelimit.OrgOverrideSet, want int64) {
	t.Helper()
	if set.OrgRPM == nil || *set.OrgRPM != want {
		t.Fatalf("org %s org-level RPM=%v want %d", orgID, set.OrgRPM, want)
	}
}

// requireNoBleed asserts that the cross-tenant poll keeps rows under their own
// org: the value another org owns must never be attributed to orgID.
func requireNoBleed(t *testing.T, all map[uuid.UUID]ratelimit.OrgOverrideSet, orgID uuid.UUID, want int64) {
	t.Helper()
	requireOrgRPM(t, orgID, all[orgID], want)
}

func seedOrgAgent(t *testing.T, db *sql.DB, name string) orgAgent {
	t.Helper()
	ctx := context.Background()
	slug := "ratelimit-" + uuid.NewString()[:8]
	var ids orgAgent
	err := runtimeconn.WithOwnerTx(ctx, db, func(tx *sql.Tx) error {
		var orgID, userID, agentID string
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		if err := tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id::text`,
			name, slug).Scan(&orgID); err != nil {
			return err
		}
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		if err := tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.users (org_id, email, name) VALUES ($1::uuid, $2, $3) RETURNING id::text`,
			orgID, slug+"@example.com", name).Scan(&userID); err != nil {
			return err
		}
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		if err := tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			 VALUES ($1::uuid, $2::uuid, $3, $4) RETURNING id::text`,
			orgID, userID, name+" Agent", "agent-"+slug).Scan(&agentID); err != nil {
			return err
		}
		ids = orgAgent{org: uuid.MustParse(orgID), agent: uuid.MustParse(agentID)}
		return nil
	})
	if err != nil {
		t.Fatalf("seed org/agent: %v", err)
	}
	return ids
}

func seedOverride(t *testing.T, db *sql.DB, seed overrideSeed) {
	t.Helper()
	ctx := context.Background()
	var agentArg any
	if seed.agentID != "" {
		agentArg = seed.agentID
	}
	err := runtimeconn.WithOwnerTx(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
			VALUES ($1::uuid, $2::uuid, $3)`, seed.orgID, agentArg, seed.rpm)
		return err
	})
	if err != nil {
		t.Fatalf("seed rate-limit override: %v", err)
	}
}
