//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/lib/pq"
)

const insertMemoryWithSessionSQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, session_id, content, content_hash, content_tokens
	) VALUES (
		$1::uuid, $2::uuid, $3::uuid, $4, $5, $6
	)
	RETURNING id::text`

const insertMemoryMinimalSQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, content, content_hash, content_tokens
	) VALUES (
		$1::uuid, $2::uuid, $3, $4, $5
	)
	RETURNING id::text, valid_from, valid_until, observed_at`

func TestMemories_TemporalColumnsAndDefaults(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	assertMemoryTemporalColumns(t, ctx, db)

	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	var id string
	var validFrom, observedAt time.Time
	var validUntil sql.NullTime
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryMinimalSQL,
			orgA, agentID, "user prefers dark mode", "hash-defaults-1", 4,
		).Scan(&id, &validFrom, &validUntil, &observedAt)
	})
	if err != nil {
		t.Fatalf("insert minimal memory: %v", err)
	}
	if id == "" {
		t.Fatal("expected memory id")
	}
	if validUntil.Valid {
		t.Fatal("expected valid_until NULL by default")
	}
	if validFrom.IsZero() || observedAt.IsZero() {
		t.Fatal("expected valid_from and observed_at defaults")
	}
}

func TestMemories_ValidIntervalCheck(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	from := time.Date(2024, 6, 1, 12, 0, 0, 0, time.UTC)
	until := from.Add(-time.Hour) // invalid: until <= from
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				valid_from, valid_until
			) VALUES ($1::uuid, $2::uuid, 'bad interval', 'hash-bad-interval', 2, $3, $4)`,
			orgA, agentID, from, until)
		return err
	})
	if err == nil {
		t.Fatal("expected valid_interval CHECK to reject valid_until <= valid_from")
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "23514" {
		t.Fatalf("expected check_violation 23514, got %v", err)
	}

	// Equal timestamps also rejected (need strictly greater).
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				valid_from, valid_until
			) VALUES ($1::uuid, $2::uuid, 'equal interval', 'hash-eq-interval', 2, $3, $3)`,
			orgA, agentID, from)
		return err
	})
	if err == nil {
		t.Fatal("expected valid_interval CHECK to reject valid_until = valid_from")
	}
}

func TestMemories_RetrospectiveValidFrom(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	validFrom := time.Now().UTC().Add(-3 * 365 * 24 * time.Hour)
	observedAt := time.Now().UTC()
	var id string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				valid_from, observed_at
			) VALUES ($1::uuid, $2::uuid, 'moved to Berlin three years ago', 'hash-berlin', 6, $3, $4)
			RETURNING id::text`,
			orgA, agentID, validFrom, observedAt).Scan(&id)
	})
	if err != nil {
		t.Fatalf("retrospective insert: %v", err)
	}
	if id == "" {
		t.Fatal("expected memory id")
	}
}

func TestRLSMemoriesIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "mem-a"})
	seedMemory(t, ctx, memorySeed{db: db, orgID: orgB, agentSlug: "agent-b", content: "mem-b"})

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: orgB, want: 1})

	// Service account sees all rows.
	var serviceCount int
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.memories`).Scan(&serviceCount)
	})
	if err != nil {
		t.Fatalf("service count: %v", err)
	}
	if serviceCount != 2 {
		t.Fatalf("expected service account count 2, got %d", serviceCount)
	}
}

func TestMemories_SoftDeletePartialIndex(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memID := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "active-then-deleted"})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.memories
			SET status = 'deleted', deleted_at = NOW()
			WHERE id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("soft delete: %v", err)
	}

	var activeCount int
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_core.memories
			WHERE org_id = $1::uuid AND status = 'active' AND deleted_at IS NULL`,
			orgA).Scan(&activeCount)
	})
	if err != nil {
		t.Fatalf("active count: %v", err)
	}
	if activeCount != 0 {
		t.Fatalf("expected 0 active memories after soft delete, got %d", activeCount)
	}

	var idxExists bool
	err = db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM pg_indexes
			WHERE schemaname = 'ibex_core' AND indexname = 'idx_memories_agent_active'
		)`).Scan(&idxExists)
	if err != nil {
		t.Fatalf("index check: %v", err)
	}
	if !idxExists {
		t.Fatal("missing idx_memories_agent_active")
	}
}

func TestMemories_SessionClearOnDelete(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	sess := seedSessionWithCheckpoint(t, ctx, sessionSeed{
		db: db, orgID: orgA, agentSlug: "agent-a", externalID: "mem-sess",
	})

	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithSessionSQL,
			orgA, sess.agentID, sess.sessionID,
			"session-scoped note", "hash-sess-mem", 3,
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory with session: %v", err)
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.sessions WHERE id = $1::uuid`, sess.sessionID)
		return err
	})
	if err != nil {
		t.Fatalf("delete session: %v", err)
	}

	var sessionID sql.NullString
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT session_id::text FROM ibex_core.memories WHERE id = $1::uuid`, memID,
		).Scan(&sessionID)
	})
	if err != nil {
		t.Fatalf("lookup memory session_id: %v", err)
	}
	if sessionID.Valid {
		t.Fatalf("expected session_id NULL after session delete, got %q", sessionID.String)
	}
}

func assertMemoryTemporalColumns(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
	type colExpect struct {
		name     string
		nullable string
		hasDef   bool
	}
	expects := []colExpect{
		{name: "valid_from", nullable: "NO", hasDef: true},
		{name: "valid_until", nullable: "YES", hasDef: false},
		{name: "observed_at", nullable: "NO", hasDef: true},
	}
	for _, e := range expects {
		var dataType, isNullable string
		var columnDefault sql.NullString
		err := db.QueryRowContext(ctx, `
			SELECT data_type, is_nullable, column_default
			FROM information_schema.columns
			WHERE table_schema = 'ibex_core' AND table_name = 'memories' AND column_name = $1`,
			e.name).Scan(&dataType, &isNullable, &columnDefault)
		if err != nil {
			t.Fatalf("column %s: %v", e.name, err)
		}
		if dataType != "timestamp with time zone" {
			t.Errorf("column %s type=%q, want timestamptz", e.name, dataType)
		}
		if isNullable != e.nullable {
			t.Errorf("column %s nullable=%q, want %q", e.name, isNullable, e.nullable)
		}
		if e.hasDef && (!columnDefault.Valid || columnDefault.String == "") {
			t.Errorf("column %s missing default", e.name)
		}
		if !e.hasDef && columnDefault.Valid && columnDefault.String != "" {
			t.Errorf("column %s unexpected default %q", e.name, columnDefault.String)
		}
	}

	var forced bool
	err := db.QueryRowContext(ctx, `
		SELECT c.relforcerowsecurity
		FROM pg_class c
		JOIN pg_namespace n ON n.oid = c.relnamespace
		WHERE n.nspname = 'ibex_core' AND c.relname = 'memories'`).Scan(&forced)
	if err != nil {
		t.Fatalf("force rls: %v", err)
	}
	if !forced {
		t.Error("expected FORCE ROW LEVEL SECURITY on ibex_core.memories")
	}
}

type memorySeed struct {
	db                       *sql.DB
	orgID, agentSlug, content string
}

func seedMemory(t *testing.T, ctx context.Context, seed memorySeed) string {
	t.Helper()
	var id string
	var validFrom, observedAt time.Time
	var validUntil sql.NullTime
	err := withServiceAccount(ctx, seed.db, func(tx *sql.Tx) error {
		var agentID string
		if err := tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents
			WHERE org_id = $1::uuid AND slug = $2`, seed.orgID, seed.agentSlug).Scan(&agentID); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, insertMemoryMinimalSQL,
			seed.orgID, agentID, seed.content, "hash-"+seed.content, 1,
		).Scan(&id, &validFrom, &validUntil, &observedAt)
	})
	if err != nil {
		t.Fatalf("seed memory org=%s: %v", seed.orgID, err)
	}
	return id
}
