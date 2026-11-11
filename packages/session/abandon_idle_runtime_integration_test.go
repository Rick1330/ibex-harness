//go:build integration

package session_test

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testutil"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/google/uuid"
)

// TestStore_AbandonIdle_AsRuntimeReturnsChangedIDs is the positive control for
// the cross-tenant sweep. ibex_runtime cannot read the sessions table across
// tenants directly, so AbandonIdle must call ibex_core.sessions_abandon_idle,
// which returns the ids it changed. Before the fix the sweep matched zero rows
// and no idle session was ever abandoned.
func TestStore_AbandonIdle_AsRuntimeReturnsChangedIDs(t *testing.T) {
	dsn := integrationDSN()
	ids := setupStore(t)

	orgB, agentB := seedOrgAgent(t, ids.db, "Org B Runtime", "org-b-runtime-"+uuid.NewString()[:8])
	idsB := storeIDs{db: ids.db, store: ids.store, orgID: orgB, agentID: agentB}

	staleA := mustCreate(t, ids, "ext-runtime-stale-a")
	freshA := mustCreate(t, ids, "ext-runtime-fresh-a")
	staleB := mustCreate(t, idsB, "ext-runtime-stale-b")
	freshB := mustCreate(t, idsB, "ext-runtime-fresh-b")

	old := time.Now().UTC().Add(-2 * time.Hour)
	backdateSessionUpdatedAt(t, ids.db, staleA.ID, old)
	backdateSessionUpdatedAt(t, ids.db, staleB.ID, old)

	testutil.ProvisionCapabilityLogins(t, dsn)
	runtimeDB := testutil.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	runtimeStore, err := session.NewPostgresStore(session.PostgresStoreDeps{
		DB: runtimeDB, Tracer: telemetry.NoopTracer("ibex-session"),
	})
	if err != nil {
		t.Fatalf("runtime store: %v", err)
	}

	idleBefore := time.Now().UTC().Add(-30 * time.Minute)
	res, err := runtimeStore.AbandonIdle(context.Background(), session.AbandonIdleParams{
		IdleBefore: idleBefore, Limit: 100,
	})
	testutil.RequireNoPermissionDenied(t, err)
	if err != nil {
		t.Fatalf("AbandonIdle as ibex_runtime: %v", err)
	}
	if res.SkippedLock {
		t.Fatal("unexpected skip lock")
	}

	// Positive: the changed ids come back for both orgs, proving the definer's
	// cross-tenant reach is what the runtime login actually executes.
	if !containsAbandoned(res.Abandoned, staleA.ID) {
		t.Fatalf("org A idle session %s missing from %+v", staleA.ID, res.Abandoned)
	}
	if !containsAbandoned(res.Abandoned, staleB.ID) {
		t.Fatalf("org B idle session %s missing from %+v", staleB.ID, res.Abandoned)
	}

	// Negative: a fresh row is never a victim, regardless of org. The sweep is
	// cross-tenant by design, so the isolation check here is predicate-level,
	// not tenant-level.
	if containsAbandoned(res.Abandoned, freshA.ID) || containsAbandoned(res.Abandoned, freshB.ID) {
		t.Fatalf("fresh session abandoned: %+v", res.Abandoned)
	}

	if got := mustReload(t, ids, "ext-runtime-stale-a"); got.Status != session.StatusAbandoned {
		t.Fatalf("org A stale status=%s", got.Status)
	}
	if got := mustReload(t, idsB, "ext-runtime-stale-b"); got.Status != session.StatusAbandoned {
		t.Fatalf("org B stale status=%s", got.Status)
	}
	if got := mustReload(t, ids, "ext-runtime-fresh-a"); got.Status != session.StatusActive {
		t.Fatalf("org A fresh status=%s", got.Status)
	}
}
