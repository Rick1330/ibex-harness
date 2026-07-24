//go:build integration

package session_test

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/google/uuid"

	_ "github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func TestStore_GetOrCreate_IdempotentExternalID(t *testing.T) {
	store, orgID, agentID := setupStore(t)
	p := session.GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: "ext-idem",
		Model: "gpt-4o", Provider: "openai",
	}
	a, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("first: %v", err)
	}
	b, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if a.ID != b.ID {
		t.Fatalf("expected same session id, got %s vs %s", a.ID, b.ID)
	}
}

func TestStore_GetOrCreate_EmptyExternalID_AlwaysNew(t *testing.T) {
	store, orgID, agentID := setupStore(t)
	p := session.GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, Model: "gpt-4o", Provider: "openai",
	}
	a, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("first: %v", err)
	}
	b, err := store.GetOrCreate(context.Background(), p)
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if a.ID == b.ID {
		t.Fatal("expected distinct sessions for empty external_id")
	}
}

func TestStore_AppendCheckpoint_AtomicStats(t *testing.T) {
	store, orgID, agentID := setupStore(t)
	sess := mustCreate(t, store, orgID, agentID, "ext-stats")
	err := store.AppendCheckpoint(context.Background(), session.CheckpointParams{
		SessionID: sess.ID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "req-1", MessagesHash: "mh1", InputTokens: 10, OutputTokens: 20,
		Model: "gpt-4o", Provider: "openai", LatencyMs: 100, IsComplete: true,
	})
	if err != nil {
		t.Fatalf("append: %v", err)
	}
	got := mustReload(t, store, orgID, agentID, "ext-stats")
	if got.TurnCount != 1 || got.TotalInputTokens != 10 || got.TotalOutputTokens != 20 || got.TotalLatencyMs != 100 {
		t.Fatalf("stats mismatch: %+v", got)
	}
}

func TestStore_AppendCheckpoint_DuplicateTurn(t *testing.T) {
	store, orgID, agentID := setupStore(t)
	sess := mustCreate(t, store, orgID, agentID, "ext-dup")
	p := session.CheckpointParams{
		SessionID: sess.ID, OrgID: orgID, AgentID: agentID, TurnIndex: 0,
		RequestID: "req-1", MessagesHash: "mh1", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	}
	if err := store.AppendCheckpoint(context.Background(), p); err != nil {
		t.Fatalf("first: %v", err)
	}
	err := store.AppendCheckpoint(context.Background(), p)
	if !errors.Is(err, session.ErrDuplicateTurn) {
		t.Fatalf("expected ErrDuplicateTurn, got %v", err)
	}
}

func TestStore_Complete(t *testing.T) {
	store, orgID, agentID := setupStore(t)
	sess := mustCreate(t, store, orgID, agentID, "ext-done")
	if err := store.Complete(context.Background(), sess.ID, orgID); err != nil {
		t.Fatalf("complete: %v", err)
	}
	got := mustReload(t, store, orgID, agentID, "ext-done")
	if got.Status != session.StatusCompleted {
		t.Fatalf("status=%s", got.Status)
	}
	if err := store.Complete(context.Background(), sess.ID, orgID); err != nil {
		t.Fatalf("noop complete: %v", err)
	}
}

func TestStore_RLS_CrossOrg(t *testing.T) {
	db, store := openStore(t)
	orgA, agentA := seedOrgAgent(t, db, "Org A", "org-a")
	orgB, _ := seedOrgAgent(t, db, "Org B", "org-b")
	sess := mustCreate(t, store, orgA, agentA, "ext-rls")

	err := store.AppendCheckpoint(context.Background(), session.CheckpointParams{
		SessionID: sess.ID, OrgID: orgB, AgentID: agentA, TurnIndex: 0,
		RequestID: "x", MessagesHash: "h", Model: "gpt-4o", Provider: "openai",
		LatencyMs: 1, IsComplete: true,
	})
	if err == nil {
		t.Fatal("expected cross-org append to fail")
	}
	err = store.Complete(context.Background(), sess.ID, orgB)
	if !errors.Is(err, session.ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func setupStore(t *testing.T) (*session.PostgresStore, uuid.UUID, uuid.UUID) {
	t.Helper()
	db, store := openStore(t)
	orgID, agentID := seedOrgAgent(t, db, "Org S", "org-s-"+uuid.NewString()[:8])
	return store, orgID, agentID
}

func openStore(t *testing.T) (*sql.DB, *session.PostgresStore) {
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
	store, err := session.NewPostgresStore(session.PostgresStoreDeps{DB: db})
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	return db, store
}

func integrationDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

func resetSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
}

func seedOrgAgent(t *testing.T, db *sql.DB, name, slug string) (uuid.UUID, uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	var orgID, userID, agentID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2)
			RETURNING id::text`, name, slug).Scan(&orgID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.users (org_id, email, name)
			VALUES ($1::uuid, $2, $3) RETURNING id::text`,
			orgID, slug+"@example.com", name).Scan(&userID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			VALUES ($1::uuid, $2::uuid, $3, $4) RETURNING id::text`,
			orgID, userID, name+" Agent", "agent-"+slug).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	return uuid.MustParse(orgID), uuid.MustParse(agentID)
}

func withServiceAccount(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func mustCreate(t *testing.T, store *session.PostgresStore, orgID, agentID uuid.UUID, ext string) *session.Session {
	t.Helper()
	sess, err := store.GetOrCreate(context.Background(), session.GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: ext, Model: "gpt-4o", Provider: "openai",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	return sess
}

func mustReload(t *testing.T, store *session.PostgresStore, orgID, agentID uuid.UUID, ext string) *session.Session {
	t.Helper()
	sess, err := store.GetOrCreate(context.Background(), session.GetOrCreateParams{
		OrgID: orgID, AgentID: agentID, ExternalID: ext, Model: "gpt-4o", Provider: "openai",
	})
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	return sess
}
