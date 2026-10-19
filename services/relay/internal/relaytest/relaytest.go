//go:build integration

// Package relaytest provides shared real-PostgreSQL fixtures for the relay
// integration tests. It is integration-tagged so non-integration builds do not
// compile it.
package relaytest

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/Rick1330/ibex-harness/services/relay/internal/fence"
	"github.com/google/uuid"

	_ "github.com/lib/pq" // PostgreSQL driver for relay integration tests
)

const defaultDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

// DSN returns POSTGRES_TEST_DSN or the local integration default.
func DSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultDSN
}

// ClickHouseDSN returns CLICKHOUSE_TEST_NATIVE_DSN (the clickhouse-go native DSN
// consumed by clickhousesink.Open), skipping when it is not configured. The CI
// coverage job provides a pinned ClickHouse service so the connected success
// path is exercised under the merged profile.
func ClickHouseDSN(t *testing.T) string {
	t.Helper()
	dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_TEST_NATIVE_DSN"))
	if dsn == "" {
		t.Skip("CLICKHOUSE_TEST_NATIVE_DSN is not set")
	}
	return dsn
}

// OpenMigratedDB opens DSN, skips when PostgreSQL is unavailable, resets the
// schema, and applies all migrations through the current head.
func OpenMigratedDB(t *testing.T) *sql.DB {
	t.Helper()
	dsn := DSN()
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
	ResetSchema(t, db)
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return db
}

// ResetSchema drops the relay-relevant schemas, migration table, and roles so a
// fresh migration run starts clean.
func ResetSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_billing CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_evidence_relay`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_service`)
}

// SeedOrgWithSession inserts an org, user, agent, and session as the service
// account and returns the org and session IDs.
func SeedOrgWithSession(t *testing.T, db *sql.DB, slug string) (orgID, sessionID uuid.UUID) {
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
		`INSERT INTO ibex_core.organizations (name, slug) VALUES ('relay-test-org-' || $1, $1) RETURNING id`,
		slug).Scan(&orgID); err != nil {
		t.Fatalf("org: %v", err)
	}
	var userID uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.users (org_id, email, name) VALUES ($1, $2, $3) RETURNING id`,
		orgID, uuid.NewString()+"@example.com", "relay-test-user").Scan(&userID); err != nil {
		t.Fatalf("user: %v", err)
	}
	var agentID uuid.UUID
	if err := tx.QueryRowContext(ctx,
		`INSERT INTO ibex_core.agents (org_id, created_by, name, slug) VALUES ($1, $2, $3, $4) RETURNING id`,
		orgID, userID, "relay-test-agent", uuid.NewString()[:8]).Scan(&agentID); err != nil {
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

// SoftDeleteSession tombstones a session as the service account.
func SoftDeleteSession(t *testing.T, db *sql.DB, sessionID uuid.UUID) {
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

// NewFence builds a session tombstone fence for the given resource version.
func NewFence(sessionID uuid.UUID, version int64) evidenceoutbox.TombstoneFence {
	return evidenceoutbox.TombstoneFence{
		ResourceType: fence.SessionResourceType, ResourceID: sessionID.String(), ResourceVersion: version,
	}
}
