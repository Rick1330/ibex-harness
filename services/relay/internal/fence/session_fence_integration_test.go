//go:build integration

package fence_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/fence"
	"github.com/Rick1330/ibex-harness/services/relay/internal/relaytest"
	"github.com/google/uuid"

	_ "github.com/lib/pq" // PostgreSQL driver for integration fence tests
)

func TestSessionFenceChecker_RealPostgresOutcomes(t *testing.T) {
	db := relaytest.OpenMigratedDB(t)
	orgA, sessionA := relaytest.SeedOrgWithSession(t, db, "session-fence-a")
	orgB, _ := relaytest.SeedOrgWithSession(t, db, "session-fence-b")
	checker, err := fence.NewSessionFenceChecker(db, ibexmetrics.NewRelay("test-relay"))
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()

	if err := checker.CheckFence(ctx, orgA, relaytest.NewFence(sessionA, 1)); err != nil {
		t.Fatalf("alive fence must pass: %v", err)
	}
	if err := checker.CheckFence(ctx, orgA, relaytest.NewFence(sessionA, 2)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("stale version: got %v", err)
	}
	if err := checker.CheckFence(ctx, orgA, relaytest.NewFence(uuid.New(), 1)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("unknown session: got %v", err)
	}
	if err := checker.CheckFence(ctx, orgB, relaytest.NewFence(sessionA, 1)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("cross-tenant session: got %v", err)
	}

	relaytest.SoftDeleteSession(t, db, sessionA)
	if err := checker.CheckFence(ctx, orgA, relaytest.NewFence(sessionA, 1)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("tombstoned pre-delete version: got %v", err)
	}
	if err := checker.CheckFence(ctx, orgA, relaytest.NewFence(sessionA, 2)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("tombstoned current version: got %v", err)
	}
}

func TestSessionFenceChecker_DatabaseErrorIsRetryable(t *testing.T) {
	db := relaytest.OpenMigratedDB(t)
	orgID, sessionID := relaytest.SeedOrgWithSession(t, db, "session-fence-down")
	broken, err := sql.Open("postgres", relaytest.DSN())
	if err != nil {
		t.Fatal(err)
	}
	_ = broken.Close()
	checker, err := fence.NewSessionFenceChecker(broken, ibexmetrics.NewRelay("test-relay"))
	if err != nil {
		t.Fatal(err)
	}
	err = checker.CheckFence(context.Background(), orgID, relaytest.NewFence(sessionID, 1))
	if err == nil {
		t.Fatal("closed pool must error")
	}
	if errors.Is(err, evidenceoutbox.ErrTombstonedResource) || errors.Is(err, evidenceoutbox.ErrUnsupportedFenceResource) {
		t.Fatalf("db error must stay retryable, got %v", err)
	}
}
