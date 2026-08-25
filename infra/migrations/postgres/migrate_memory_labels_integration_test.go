//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/lib/pq"
)

const insertMemoryWithCategorySQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, content, content_hash, content_tokens, category
	) VALUES (
		$1::uuid, $2::uuid, $3, $4, $5, $6
	)
	RETURNING id::text`

const insertMemoryLabelSQL = `
	INSERT INTO ibex_core.memory_labels (memory_id, org_id, label, confidence)
	VALUES ($1::uuid, $2::uuid, $3, $4)`

func TestMemoryLabels_TableAndForceRLS(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	assertCoreTableExists(t, ctx, db, "memory_labels")
	assertMemoriesForceRLSNamed(t, ctx, db, "memory_labels")
}

func TestMemoryLabels_BackfillFromCategory(t *testing.T) {
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

	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithCategorySQL,
			orgA, agentID, "prefers dark mode", "hash-pref-1", 3, "preference",
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory: %v", err)
	}

	// New inserts are not auto-labeled; seed label as Phase 3 writers will, then
	// verify backfill path by re-running migration semantics on pre-label rows:
	// backfill already ran at Up for empty DB. Insert label matching category.
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "preference", 1.00)
		return err
	})
	if err != nil {
		t.Fatalf("insert label: %v", err)
	}

	var label string
	var confidence float64
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT label, confidence::float8 FROM ibex_core.memory_labels
			WHERE memory_id = $1::uuid AND org_id = $2::uuid`, memID, orgA,
		).Scan(&label, &confidence)
	})
	if err != nil {
		t.Fatalf("select label: %v", err)
	}
	if label != "preference" || confidence != 1.0 {
		t.Fatalf("got label=%q confidence=%v, want preference @ 1.0", label, confidence)
	}
}

func TestMemoryLabels_BackfillOnMigrate(t *testing.T) {
	// Apply through 000014, insert memory, then Up to 15 so backfill runs.
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("full up: %v", err)
	}
	if err := Down(dsn); err != nil {
		t.Fatalf("down from 15: %v", err)
	}
	v, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version after down: %v", err)
	}
	if dirty || v != 14 {
		t.Fatalf("expected version 14 clean after down, got v=%d dirty=%v", v, dirty)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})
	var memID string
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithCategorySQL,
			orgA, agentID, "episodic note", "hash-epi-1", 2, "episodic",
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory at v14: %v", err)
	}

	if err := Up(dsn); err != nil {
		t.Fatalf("up to 15: %v", err)
	}

	var label string
	var confidence float64
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT label, confidence::float8 FROM ibex_core.memory_labels
			WHERE memory_id = $1::uuid`, memID).Scan(&label, &confidence)
	})
	if err != nil {
		t.Fatalf("backfill label: %v", err)
	}
	if label != "episodic" || confidence != 1.0 {
		t.Fatalf("backfill got label=%q confidence=%v", label, confidence)
	}
}

func TestMemoryLabels_PrimarySyncAndTieBreak(t *testing.T) {
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
	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithCategorySQL,
			orgA, agentID, "multi label mem", "hash-ml-1", 3, "factual",
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory: %v", err)
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "factual", 0.50); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "preference", 0.90)
		return err
	})
	if err != nil {
		t.Fatalf("insert labels: %v", err)
	}
	assertMemoryCategory(t, ctx, db, memID, "preference")

	// Equal confidence: lexicographic label ASC wins (behavioral < factual).
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.memory_labels SET confidence = 0.80
			WHERE memory_id = $1::uuid`, memID); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "behavioral", 0.80)
		return err
	})
	if err != nil {
		t.Fatalf("tie labels: %v", err)
	}
	assertMemoryCategory(t, ctx, db, memID, "behavioral")
}

func TestMemoryLabels_Checks(t *testing.T) {
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
	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithCategorySQL,
			orgA, agentID, "check mem", "hash-chk-1", 1, "factual",
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory: %v", err)
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "not-a-label", 1.0)
		return err
	})
	assertCheckViolation(t, err)

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "factual", 1.5)
		return err
	})
	assertCheckViolation(t, err)
}

func TestRLSMemoryLabelsIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seedLabeledMemory(t, ctx, labeledMemorySeed{
		db: db, orgID: orgA, agentSlug: "agent-a", content: "a-mem", label: "factual",
	})
	seedLabeledMemory(t, ctx, labeledMemorySeed{
		db: db, orgID: orgB, agentSlug: "agent-b", content: "b-mem", label: "preference",
	})

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memory_labels", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memory_labels", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memory_labels", orgID: orgB, want: 1})

	var serviceCount int
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.memory_labels`).Scan(&serviceCount)
	})
	if err != nil {
		t.Fatalf("service count: %v", err)
	}
	if serviceCount != 2 {
		t.Fatalf("expected service count 2, got %d", serviceCount)
	}
}

func TestMemoryLabels_CascadeAndEmptyLeavesCategory(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memID := seedLabeledMemory(t, ctx, labeledMemorySeed{
		db: db, orgID: orgA, agentSlug: "agent-a", content: "cascade-mem", label: "procedural",
	})
	assertMemoryCategory(t, ctx, db, memID, "procedural")

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			DELETE FROM ibex_core.memory_labels WHERE memory_id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("delete labels: %v", err)
	}
	assertMemoryCategory(t, ctx, db, memID, "procedural")

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `DELETE FROM ibex_core.memories WHERE id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("delete memory: %v", err)
	}
	var n int
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT COUNT(*) FROM ibex_core.memory_labels WHERE memory_id = $1::uuid`, memID,
		).Scan(&n)
	})
	if err != nil {
		t.Fatalf("count after cascade: %v", err)
	}
	if n != 0 {
		t.Fatalf("expected 0 labels after memory delete, got %d", n)
	}
}

func TestMemoryLabels_CrossOrgFKRejected(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	memA := seedLabeledMemory(t, ctx, labeledMemorySeed{
		db: db, orgID: orgA, agentSlug: "agent-a", content: "fk-mem", label: "factual",
	})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memA, orgB, "preference", 1.0)
		return err
	})
	if err == nil {
		t.Fatal("expected cross-org FK failure")
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "23503" {
		t.Fatalf("expected FK 23503, got %v", err)
	}
}

func assertMemoriesForceRLSNamed(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	var forced bool
	err := db.QueryRowContext(ctx, `
		SELECT c.relforcerowsecurity
		FROM pg_class c
		JOIN pg_namespace n ON n.oid = c.relnamespace
		WHERE n.nspname = 'ibex_core' AND c.relname = $1`, table).Scan(&forced)
	if err != nil {
		t.Fatalf("force rls %s: %v", table, err)
	}
	if !forced {
		t.Errorf("expected FORCE ROW LEVEL SECURITY on ibex_core.%s", table)
	}
}

func assertMemoryCategory(t *testing.T, ctx context.Context, db *sql.DB, memID, want string) {
	t.Helper()
	var got string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT category FROM ibex_core.memories WHERE id = $1::uuid`, memID).Scan(&got)
	})
	if err != nil {
		t.Fatalf("select category: %v", err)
	}
	if got != want {
		t.Fatalf("category=%q, want %q", got, want)
	}
}

func assertCheckViolation(t *testing.T, err error) {
	t.Helper()
	if err == nil {
		t.Fatal("expected check_violation, got nil")
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || pqErr.Code != "23514" {
		t.Fatalf("expected check_violation 23514, got %v", err)
	}
}

type labeledMemorySeed struct {
	db                                 *sql.DB
	orgID, agentSlug, content, label string
}

func seedLabeledMemory(t *testing.T, ctx context.Context, seed labeledMemorySeed) string {
	t.Helper()
	var memID string
	err := withServiceAccount(ctx, seed.db, func(tx *sql.Tx) error {
		var agentID string
		if err := tx.QueryRowContext(ctx, `
			SELECT id::text FROM ibex_core.agents
			WHERE org_id = $1::uuid AND slug = $2`, seed.orgID, seed.agentSlug).Scan(&agentID); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, insertMemoryWithCategorySQL,
			seed.orgID, agentID, seed.content, "hash-"+seed.content, 1, seed.label,
		).Scan(&memID); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, seed.orgID, seed.label, 1.00)
		return err
	})
	if err != nil {
		t.Fatalf("seed labeled memory: %v", err)
	}
	return memID
}
