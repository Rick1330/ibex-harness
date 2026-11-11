//go:build integration

package session_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
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
	idsB := secondOrg(t, ids)
	want := seedRuntimeSessions(t, ids, idsB)
	backdateRuntimeSessions(t, ids.db, want.staleA, want.staleB)

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()
	store := newRuntimeStore(t, runtimeDB)

	res := abandonIdleAsRuntime(t, store)
	assertChangedIDs(t, res, []uuid.UUID{want.staleA, want.staleB})
	assertUnchangedIDs(t, res, []uuid.UUID{want.freshA, want.freshB})
	requireStatus(t, mustReload(t, ids, "ext-runtime-stale-a"), session.StatusAbandoned)
	requireStatus(t, mustReload(t, idsB, "ext-runtime-stale-b"), session.StatusAbandoned)
	requireStatus(t, mustReload(t, ids, "ext-runtime-fresh-a"), session.StatusActive)
}

type runtimeSessions struct {
	staleA uuid.UUID
	freshA uuid.UUID
	staleB uuid.UUID
	freshB uuid.UUID
}

func secondOrg(t *testing.T, ids storeIDs) storeIDs {
	t.Helper()
	orgB, agentB := seedOrgAgent(t, ids.db, "Org B Runtime", "org-b-runtime-"+uuid.NewString()[:8])
	return storeIDs{db: ids.db, store: ids.store, orgID: orgB, agentID: agentB}
}

func seedRuntimeSessions(t *testing.T, ids, idsB storeIDs) runtimeSessions {
	t.Helper()
	return runtimeSessions{
		staleA: mustCreate(t, ids, "ext-runtime-stale-a").ID,
		freshA: mustCreate(t, ids, "ext-runtime-fresh-a").ID,
		staleB: mustCreate(t, idsB, "ext-runtime-stale-b").ID,
		freshB: mustCreate(t, idsB, "ext-runtime-fresh-b").ID,
	}
}

func backdateRuntimeSessions(t *testing.T, db *sql.DB, ids ...uuid.UUID) {
	t.Helper()
	old := time.Now().UTC().Add(-2 * time.Hour)
	for _, id := range ids {
		backdateSessionUpdatedAt(t, db, id, old)
	}
}

func newRuntimeStore(t *testing.T, db *sql.DB) *session.PostgresStore {
	t.Helper()
	store, err := session.NewPostgresStore(session.PostgresStoreDeps{
		DB: db, Tracer: telemetry.NoopTracer("ibex-session"),
	})
	if err != nil {
		t.Fatalf("runtime store: %v", err)
	}
	return store
}

func abandonIdleAsRuntime(t *testing.T, store *session.PostgresStore) session.AbandonIdleResult {
	t.Helper()
	res, err := store.AbandonIdle(context.Background(), session.AbandonIdleParams{
		IdleBefore: time.Now().UTC().Add(-30 * time.Minute), Limit: 100,
	})
	runtimeconn.RequireNoPermissionDenied(t, err, "AbandonIdle")
	if err != nil {
		t.Fatalf("AbandonIdle as ibex_runtime: %v", err)
	}
	if res.SkippedLock {
		t.Fatal("unexpected skip lock")
	}
	return res
}

// assertChangedIDs covers the positive control: the changed ids come back for
// both orgs, proving the definer's cross-tenant reach is what the runtime login
// actually executes.
func assertChangedIDs(t *testing.T, res session.AbandonIdleResult, want []uuid.UUID) {
	t.Helper()
	for _, id := range want {
		if !containsAbandoned(res.Abandoned, id) {
			t.Fatalf("idle session %s missing from %+v", id, res.Abandoned)
		}
	}
}

// assertUnchangedIDs covers the predicate-level negative: a fresh row is never a
// victim, regardless of org. The sweep is cross-tenant by design.
func assertUnchangedIDs(t *testing.T, res session.AbandonIdleResult, unwanted []uuid.UUID) {
	t.Helper()
	for _, id := range unwanted {
		if containsAbandoned(res.Abandoned, id) {
			t.Fatalf("fresh session %s abandoned: %+v", id, res.Abandoned)
		}
	}
}

func requireStatus(t *testing.T, got *session.Session, want string) {
	t.Helper()
	if got.Status != want {
		t.Fatalf("status=%s want %s", got.Status, want)
	}
}
