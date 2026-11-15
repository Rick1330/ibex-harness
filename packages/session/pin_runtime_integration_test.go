//go:build integration

package session_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/session"
)

// TestStore_GetOrCreate_AsRuntimePinsTenantRole is the positive control for the
// pin on a write path. ibex_runtime holds no table grant, so the upsert reaches
// ibex_core.sessions only because the transaction assumes ibex_app; before the
// pin this is 42501.
//
// The tenant assertion is a shared external id: two orgs that present the same
// X-IBEX-Session-ID must each resolve their own row. Reuse across orgs would
// mean the org predicate or the RLS scope was dropped.
func TestStore_GetOrCreate_AsRuntimePinsTenantRole(t *testing.T) {
	ids := setupStore(t)
	idsB := secondOrg(t, ids)
	dsn := integrationDSN()

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()
	store := newRuntimeStore(t, runtimeDB)

	const externalID = "pin-shared-external-id"
	firstA := createSessionAsRuntime(t, store, baseParams(ids, externalID))
	firstB := createSessionAsRuntime(t, store, baseParams(idsB, externalID))
	if firstA.ID == firstB.ID {
		t.Fatalf("org B resolved org A's session %s: the tenant pin or the org predicate is missing", firstA.ID)
	}

	// Each org keeps resolving its own row, so the isolation is not one-way.
	againA := createSessionAsRuntime(t, store, baseParams(ids, externalID))
	if againA.ID != firstA.ID {
		t.Fatalf("org A resolved %s after creating %s", againA.ID, firstA.ID)
	}
	againB := createSessionAsRuntime(t, store, baseParams(idsB, externalID))
	if againB.ID != firstB.ID {
		t.Fatalf("org B resolved %s after creating %s", againB.ID, firstB.ID)
	}
}

func createSessionAsRuntime(t *testing.T, store *session.PostgresStore, params session.GetOrCreateParams) *session.Session {
	t.Helper()
	got, err := store.GetOrCreate(context.Background(), params)
	runtimeconn.RequireNoPermissionDenied(t, err, "GetOrCreate")
	if err != nil {
		t.Fatalf("GetOrCreate as ibex_runtime: %v", err)
	}
	return got
}
