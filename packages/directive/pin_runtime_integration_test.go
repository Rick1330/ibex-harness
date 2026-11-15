//go:build integration

package directive_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/google/uuid"
)

// TestPostgresStore_Load_AsRuntimePinsTenantRole is the positive control for
// the pin. ibex_runtime is NOINHERIT and holds no table grant of its own, so
// Load can reach ibex_core.directives only because the transaction assumes
// ibex_app first. Before the pin this read is SQLSTATE 42501, not an empty
// directive, and the caller cannot tell the two apart.
func TestPostgresStore_Load_AsRuntimePinsTenantRole(t *testing.T) {
	db, dsn := openIntegrationDB(t)
	defer func() { _ = db.Close() }()

	orgA := seedAgentDirective(t, agentDirectiveSeed{
		db: db, orgName: "Pin Org A", orgSlug: "pin-directive-a-" + uuid.NewString()[:8], content: "directive-a",
	})
	orgB := seedAgentDirective(t, agentDirectiveSeed{
		db: db, orgName: "Pin Org B", orgSlug: "pin-directive-b-" + uuid.NewString()[:8], content: "directive-b",
	})

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	store, err := directive.NewPostgresStore(runtimeDB)
	if err != nil {
		t.Fatalf("store: %v", err)
	}

	own := loadDirective(t, store, loadTarget{orgID: orgA.orgID, agentID: orgA.agentID, label: "org A"})
	if own.Content != orgA.content {
		t.Fatalf("org A content=%q want %q", own.Content, orgA.content)
	}

	// Org B's directive must not be reachable from org A's scope.
	cross := loadDirective(t, store, loadTarget{orgID: orgA.orgID, agentID: orgB.agentID, label: "org A / org B agent"})
	if cross.HasContent() {
		t.Fatalf("org A saw org B's directive: %+v", cross)
	}

	other := loadDirective(t, store, loadTarget{orgID: orgB.orgID, agentID: orgB.agentID, label: "org B"})
	if other.Content != orgB.content {
		t.Fatalf("org B content=%q want %q", other.Content, orgB.content)
	}
}

// loadTarget is one directive read over the runtime login: whose scope, and a
// label naming it in failure messages.
type loadTarget struct {
	orgID   uuid.UUID
	agentID uuid.UUID
	label   string
}

// loadDirective issues the read over the ibex_runtime connection and fails the
// test if the pin let a permission denial through.
func loadDirective(t *testing.T, store *directive.PostgresStore, target loadTarget) directive.Resolved {
	t.Helper()
	got, err := store.Load(context.Background(), target.orgID, target.agentID)
	runtimeconn.RequireNoPermissionDenied(t, err, "Load("+target.label+")")
	if err != nil {
		t.Fatalf("Load(%s) as ibex_runtime: %v", target.label, err)
	}
	return got
}
