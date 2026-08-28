//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

const insertMemoryForEscalationSQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, content, content_hash, content_tokens, category
	) VALUES (
		$1::uuid, $2::uuid, $3, $4, 1, 'factual'
	)
	RETURNING id::text`

const insertConflictEscalationSQL = `
	INSERT INTO ibex_core.memory_conflict_escalations (
		org_id, new_memory_id, candidate_memory_id, conflict_type
	) VALUES ($1::uuid, $2::uuid, $3::uuid, $4)`

type escalationMemorySeed struct {
	orgID, agentID, newContent, candidateContent string
}

type conflictEscalationsDB struct {
	t  *testing.T
	db *sql.DB
}

func openMigratedConflictEscalationsDB(t *testing.T) *conflictEscalationsDB {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		db.Close()
		t.Fatalf("up: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return &conflictEscalationsDB{t: t, db: db}
}

func (f *conflictEscalationsDB) insertMemory(orgID, agentID, content string) string {
	f.t.Helper()
	var memID string
	err := withServiceAccount(context.Background(), f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), insertMemoryForEscalationSQL,
			orgID, agentID, content, "hash-"+content,
		).Scan(&memID)
	})
	if err != nil {
		f.t.Fatalf("insert memory: %v", err)
	}
	return memID
}

func (f *conflictEscalationsDB) insertEscalation(orgID, newID, candidateID string) {
	f.t.Helper()
	err := withServiceAccount(context.Background(), f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), insertConflictEscalationSQL,
			orgID, newID, candidateID, "escalate_pending")
		return err
	})
	if err != nil {
		f.t.Fatalf("insert escalation: %v", err)
	}
}

func TestRLSMemoryConflictEscalationsIsolation(t *testing.T) {
	f := openMigratedConflictEscalationsDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, context.Background(), f.db)
	agentA := lookupAgentID(t, context.Background(), agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	agentB := lookupAgentID(t, context.Background(), agentLookup{db: f.db, orgID: orgB, slug: "agent-b"})

	newA := f.insertMemory(orgA, agentA, "new-a")
	candA := f.insertMemory(orgA, agentA, "cand-a")
	newB := f.insertMemory(orgB, agentB, "new-b")
	candB := f.insertMemory(orgB, agentB, "cand-b")
	f.insertEscalation(orgA, newA, candA)
	f.insertEscalation(orgB, newB, candB)

	assertTableCount(t, context.Background(), tableCountCheck{
		db: f.db, table: "memory_conflict_escalations", orgID: "", want: 0,
	})
	assertTableCount(t, context.Background(), tableCountCheck{
		db: f.db, table: "memory_conflict_escalations", orgID: orgA, want: 1,
	})
	assertTableCount(t, context.Background(), tableCountCheck{
		db: f.db, table: "memory_conflict_escalations", orgID: orgB, want: 1,
	})

	// Org B cannot read or modify Org A's escalation row.
	var escAID string
	err := withServiceAccount(context.Background(), f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `
			SELECT id::text FROM ibex_core.memory_conflict_escalations
			WHERE org_id = $1::uuid LIMIT 1`, orgA).Scan(&escAID)
	})
	if err != nil {
		t.Fatalf("load org A escalation: %v", err)
	}

	var updated int64
	err = withAppRole(context.Background(), f.db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(context.Background(),
			`SELECT set_config('app.current_org_id', $1, true)`, orgB); err != nil {
			return err
		}
		res, err := tx.ExecContext(context.Background(), `
			UPDATE ibex_core.memory_conflict_escalations
			SET status = 'resolved'
			WHERE id = $1::uuid`, escAID)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		updated = n
		return nil
	})
	if err != nil {
		t.Fatalf("cross-tenant update: %v", err)
	}
	if updated != 0 {
		t.Fatalf("expected 0 rows updated across tenants, got %d", updated)
	}
}
