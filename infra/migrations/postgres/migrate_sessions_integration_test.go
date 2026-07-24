//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

const insertSessionSQL = `
	INSERT INTO ibex_core.sessions (org_id, agent_id, model, provider, external_id)
	VALUES ($1::uuid, $2::uuid, 'gpt-4o', 'openai', $3)
	RETURNING id::text`

const insertCheckpointSQL = `
	INSERT INTO ibex_core.checkpoints (
		session_id, org_id, agent_id, turn_index, request_id,
		messages_hash, input_tokens, output_tokens, model, provider,
		latency_ms, is_streaming, is_complete
	) VALUES (
		$1::uuid, $2::uuid, $3::uuid, $4, $5,
		$6, 10, 20, 'gpt-4o', 'openai',
		100, false, true
	)
	RETURNING id::text`

func TestRLSSessionsIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seedSessionWithCheckpoint(t, ctx, sessionSeed{db: db, orgID: orgA, agentSlug: "agent-a", externalID: "ext-a"})
	seedSessionWithCheckpoint(t, ctx, sessionSeed{db: db, orgID: orgB, agentSlug: "agent-b", externalID: "ext-b"})

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "sessions", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "sessions", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "sessions", orgID: orgB, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "checkpoints", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "checkpoints", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "checkpoints", orgID: orgB, want: 1})
}

func TestCheckpointsUniqueTurnIndex(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	seeded := seedSessionWithCheckpoint(t, ctx, sessionSeed{
		db: db, orgID: orgA, agentSlug: "agent-a", externalID: "ext-dup",
	})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertCheckpointSQL,
			seeded.sessionID, orgA, seeded.agentID, 0, "req-dup", "hash-dup")
		return err
	})
	if err == nil {
		t.Fatal("expected duplicate (session_id, turn_index) to fail")
	}
}

func TestCheckpointsAppendOnly(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	seedSessionWithCheckpoint(t, ctx, sessionSeed{
		db: db, orgID: orgA, agentSlug: "agent-a", externalID: "ext-ao",
	})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `UPDATE ibex_core.checkpoints SET latency_ms = 999`)
		return err
	})
	if err == nil {
		t.Fatal("expected append-only update to fail")
	}

	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.checkpoints`)
		return err
	})
	if err == nil {
		t.Fatal("expected ibex_app DELETE on checkpoints to fail")
	}
}

func TestSessionsCompositeFKOwnership(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	agentB := lookupAgentID(t, ctx, db, orgB, "agent-b")

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertSessionSQL, orgA, agentB, "cross-org")
		return err
	})
	if err == nil {
		t.Fatal("expected cross-org agent_id FK to fail")
	}

	seeded := seedSessionWithCheckpoint(t, ctx, sessionSeed{
		db: db, orgID: orgA, agentSlug: "agent-a", externalID: "ext-fk",
	})
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertCheckpointSQL,
			seeded.sessionID, orgB, seeded.agentID, 1, "req-cross", "hash-cross")
		return err
	})
	if err == nil {
		t.Fatal("expected cross-org session checkpoint FK to fail")
	}
}

func TestSessionsExtractionIndexExists(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	var exists bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM pg_indexes
			WHERE schemaname = 'ibex_core'
			  AND indexname = 'idx_sessions_agent_extraction'
		)`).Scan(&exists)
	if err != nil {
		t.Fatalf("check extraction index: %v", err)
	}
	if !exists {
		t.Fatal("missing idx_sessions_agent_extraction")
	}
}

type sessionSeed struct {
	db                           *sql.DB
	orgID, agentSlug, externalID string
}

type seededSession struct {
	sessionID string
	agentID   string
}

func seedSessionWithCheckpoint(t *testing.T, ctx context.Context, seed sessionSeed) seededSession {
	t.Helper()
	var out seededSession
	err := withServiceAccount(ctx, seed.db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents
			WHERE org_id = $1::uuid AND slug = $2`, seed.orgID, seed.agentSlug).Scan(&out.agentID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, insertSessionSQL,
			seed.orgID, out.agentID, seed.externalID).Scan(&out.sessionID); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, insertCheckpointSQL,
			out.sessionID, seed.orgID, out.agentID, 0, "req-"+seed.externalID, "hash-"+seed.externalID)
		return err
	})
	if err != nil {
		t.Fatalf("seed session org=%s: %v", seed.orgID, err)
	}
	return out
}

func lookupAgentID(t *testing.T, ctx context.Context, db *sql.DB, orgID, slug string) string {
	t.Helper()
	var agentID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents
			WHERE org_id = $1::uuid AND slug = $2`, orgID, slug).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("lookup agent: %v", err)
	}
	return agentID
}
