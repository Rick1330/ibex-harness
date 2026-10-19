//go:build integration

package fence_test

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/relay/internal/fence"
	"github.com/google/uuid"

	_ "github.com/lib/pq" // PostgreSQL driver for integration fence tests
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

func openMigratedDB(t *testing.T) *sql.DB {
	t.Helper()
	dsn := integrationDSN()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Skipf("postgres not available: %v", err)
	}
	resetSchema(t, db)
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return db
}

func resetSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_billing CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_evidence_relay`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_service`)
}

func seedOrgWithSession(t *testing.T, db *sql.DB, slug string) (orgID, sessionID uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("service account: %v", err)
	}
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id`,
		"fence-org-"+slug, slug).Scan(&orgID); err != nil {
		t.Fatalf("org: %v", err)
	}
	var userID uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.users (org_id, email, name) VALUES ($1, $2, $3) RETURNING id`,
		orgID, uuid.NewString()+"@example.com", "fence-user").Scan(&userID); err != nil {
		t.Fatalf("user: %v", err)
	}
	var agentID uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.agents (org_id, created_by, name, slug) VALUES ($1, $2, $3, $4) RETURNING id`,
		orgID, userID, "fence-agent", uuid.NewString()[:8]).Scan(&agentID); err != nil {
		t.Fatalf("agent: %v", err)
	}
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider) VALUES ($1, $2, 'gpt-4o', 'openai') RETURNING id`,
		orgID, agentID).Scan(&sessionID); err != nil {
		t.Fatalf("session: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
	return orgID, sessionID
}

func softDeleteSession(t *testing.T, db *sql.DB, sessionID uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("service account: %v", err)
	}
	if _, err := tx.ExecContext(ctx,
		`UPDATE ibex_core.sessions SET deleted_at = NOW() WHERE id = $1`, sessionID); err != nil {
		t.Fatalf("soft delete: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatal(err)
	}
}

func newFence(orgID, sessionID uuid.UUID, version int64) evidenceoutbox.TombstoneFence {
	return evidenceoutbox.TombstoneFence{
		ResourceType: fence.SessionResourceType, ResourceID: sessionID.String(), ResourceVersion: version,
	}
}

func TestSessionFenceChecker_RealPostgresOutcomes(t *testing.T) {
	db := openMigratedDB(t)
	orgA, sessionA := seedOrgWithSession(t, db, "session-fence-a")
	orgB, _ := seedOrgWithSession(t, db, "session-fence-b")
	checker, err := fence.NewSessionFenceChecker(db, ibexmetrics.NewRelay("test-relay"))
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()

	if err := checker.CheckFence(ctx, orgA, newFence(orgA, sessionA, 1)); err != nil {
		t.Fatalf("alive fence must pass: %v", err)
	}
	if err := checker.CheckFence(ctx, orgA, newFence(orgA, sessionA, 2)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("stale version: got %v", err)
	}
	if err := checker.CheckFence(ctx, orgA, newFence(orgA, uuid.New(), 1)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("unknown session: got %v", err)
	}
	if err := checker.CheckFence(ctx, orgB, newFence(orgB, sessionA, 1)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("cross-tenant session: got %v", err)
	}

	softDeleteSession(t, db, sessionA)
	if err := checker.CheckFence(ctx, orgA, newFence(orgA, sessionA, 1)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("tombstoned pre-delete version: got %v", err)
	}
	if err := checker.CheckFence(ctx, orgA, newFence(orgA, sessionA, 2)); !errors.Is(err, evidenceoutbox.ErrTombstonedResource) {
		t.Fatalf("tombstoned current version: got %v", err)
	}
}

func TestSessionFenceChecker_DatabaseErrorIsRetryable(t *testing.T) {
	db := openMigratedDB(t)
	orgID, sessionID := seedOrgWithSession(t, db, "session-fence-down")
	broken, err := sql.Open("postgres", integrationDSN())
	if err != nil {
		t.Fatal(err)
	}
	_ = broken.Close()
	checker, err := fence.NewSessionFenceChecker(broken, ibexmetrics.NewRelay("test-relay"))
	if err != nil {
		t.Fatal(err)
	}
	err = checker.CheckFence(context.Background(), orgID, newFence(orgID, sessionID, 1))
	if err == nil {
		t.Fatal("closed pool must error")
	}
	if errors.Is(err, evidenceoutbox.ErrTombstonedResource) || errors.Is(err, evidenceoutbox.ErrUnsupportedFenceResource) {
		t.Fatalf("db error must stay retryable, got %v", err)
	}
}
