//go:build integration

package modelpolicy_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/google/uuid"
)

// TestStore_LoadOrg_AsRuntimePinsTenantRole is the positive control for the
// pin. LoadOrg reads org_model_policies as ibex_app for the transaction; the
// runtime login holds no table grant, so a missing pin is 42501 rather than an
// empty policy set that would silently deny every model.
func TestStore_LoadOrg_AsRuntimePinsTenantRole(t *testing.T) {
	db := openIntegrationDB(t)
	defer func() { _ = db.Close() }()

	suffix := uuid.NewString()[:8]
	orgA := seedOrg(t, db, "pin-modelpolicy-a-"+suffix)
	orgB := seedOrg(t, db, "pin-modelpolicy-b-"+suffix)
	insertPolicy(t, db, orgA, policySeed{pattern: "gpt-pin-a*", allowed: true, priority: 1})
	insertPolicy(t, db, orgB, policySeed{pattern: "gpt-pin-b*", allowed: true, priority: 1})

	pgprovision.CapabilityLogins(t, integrationDSN())
	runtimeDB := runtimeconn.OpenRuntimeDB(t, integrationDSN())
	defer func() { _ = runtimeDB.Close() }()

	store := mustStore(t, runtimeDB)

	own := loadPolicies(t, store, orgA, "org A")
	requirePattern(t, own.Policies, "gpt-pin-a*")
	requireNoPattern(t, own.Policies, "gpt-pin-b*")

	other := loadPolicies(t, store, orgB, "org B")
	requirePattern(t, other.Policies, "gpt-pin-b*")
	requireNoPattern(t, other.Policies, "gpt-pin-a*")
}

func loadPolicies(t *testing.T, store *modelpolicy.Store, orgID uuid.UUID, label string) modelpolicy.OrgPolicies {
	t.Helper()
	got, err := store.LoadOrg(context.Background(), orgID)
	runtimeconn.RequireNoPermissionDenied(t, err, "LoadOrg("+label+")")
	if err != nil {
		t.Fatalf("LoadOrg(%s) as ibex_runtime: %v", label, err)
	}
	return got
}

func requirePattern(t *testing.T, policies []modelpolicy.Policy, want string) {
	t.Helper()
	for _, p := range policies {
		if p.Pattern == want {
			return
		}
	}
	t.Fatalf("policy %q missing from %+v", want, policies)
}

func requireNoPattern(t *testing.T, policies []modelpolicy.Policy, unwanted string) {
	t.Helper()
	for _, p := range policies {
		if p.Pattern == unwanted {
			t.Fatalf("cross-tenant policy %q visible in %+v", unwanted, policies)
		}
	}
}
