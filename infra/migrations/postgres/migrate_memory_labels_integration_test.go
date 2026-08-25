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

const selectMemoryLabelSQL = `
	SELECT label, confidence::float8 FROM ibex_core.memory_labels
	WHERE memory_id = $1::uuid`

type labelsDB struct {
	t   *testing.T
	dsn string
	db  *sql.DB
	ctx context.Context
}

type memoryWithCategory struct {
	orgID, agentID, content, category string
	tokens                            int
}

type memoryLabelWrite struct {
	memID, orgID, label string
	confidence          float64
}

type memoryLabelRow struct {
	label      string
	confidence float64
}

type sqlStateExpect struct {
	code string
}

func openMigratedLabelsDB(t *testing.T) *labelsDB {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		db.Close()
		t.Fatalf("up: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return &labelsDB{t: t, dsn: dsn, db: db, ctx: context.Background()}
}

func (f *labelsDB) mustDownTo(version uint) {
	f.t.Helper()
	if err := Down(f.dsn); err != nil {
		f.t.Fatalf("down: %v", err)
	}
	v, dirty, err := Version(f.dsn)
	if err != nil {
		f.t.Fatalf("version: %v", err)
	}
	if dirty || v != version {
		f.t.Fatalf("expected version %d clean, got v=%d dirty=%v", version, v, dirty)
	}
}

func (f *labelsDB) mustUp() {
	f.t.Helper()
	if err := Up(f.dsn); err != nil {
		f.t.Fatalf("up: %v", err)
	}
}

func (f *labelsDB) insertMemory(m memoryWithCategory) string {
	f.t.Helper()
	var memID string
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, insertMemoryWithCategorySQL,
			m.orgID, m.agentID, m.content, "hash-"+m.content, m.tokens, m.category,
		).Scan(&memID)
	})
	if err != nil {
		f.t.Fatalf("insert memory: %v", err)
	}
	return memID
}

func (f *labelsDB) insertLabel(w memoryLabelWrite) error {
	f.t.Helper()
	return withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, insertMemoryLabelSQL, w.memID, w.orgID, w.label, w.confidence)
		return err
	})
}

func (f *labelsDB) mustInsertLabel(w memoryLabelWrite) {
	f.t.Helper()
	if err := f.insertLabel(w); err != nil {
		f.t.Fatalf("insert label %s: %v", w.label, err)
	}
}

func (f *labelsDB) firstLabel(memID string) memoryLabelRow {
	f.t.Helper()
	var row memoryLabelRow
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, selectMemoryLabelSQL, memID).Scan(&row.label, &row.confidence)
	})
	if err != nil {
		f.t.Fatalf("select label: %v", err)
	}
	return row
}

func (f *labelsDB) assertCategory(check memoryCategoryCheck) {
	f.t.Helper()
	assertMemoryCategory(f.t, f.ctx, check)
}

func (f *labelsDB) assertReject(err error, want sqlStateExpect) {
	f.t.Helper()
	assertPQCode(f.t, err, want)
}

func TestMemoryLabels_TableAndForceRLS(t *testing.T) {
	f := openMigratedLabelsDB(t)
	assertCoreTableExists(t, f.ctx, f.db, "memory_labels")
	assertCoreTableRLS(t, f.ctx, coreTableRLSCheck{
		db: f.db, table: "memory_labels", expect: coreTableRLSFlags{forced: true},
	})
}

func TestMemoryLabels_BackfillOnMigrate(t *testing.T) {
	f := openMigratedLabelsDB(t)
	f.mustDownTo(14)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentID := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	memID := f.insertMemory(memoryWithCategory{
		orgID: orgA, agentID: agentID, content: "episodic note", category: "episodic", tokens: 2,
	})

	f.mustUp()

	got := f.firstLabel(memID)
	if got.label != "episodic" || got.confidence != 1.0 {
		t.Fatalf("backfill got label=%q confidence=%v, want episodic @ 1.0", got.label, got.confidence)
	}
}

func TestMemoryLabels_PrimarySyncAndTieBreak(t *testing.T) {
	f := openMigratedLabelsDB(t)
	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentID := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	memID := f.insertMemory(memoryWithCategory{
		orgID: orgA, agentID: agentID, content: "multi label mem", category: "factual", tokens: 3,
	})

	f.mustInsertLabel(memoryLabelWrite{memID: memID, orgID: orgA, label: "factual", confidence: 0.50})
	f.mustInsertLabel(memoryLabelWrite{memID: memID, orgID: orgA, label: "preference", confidence: 0.90})
	f.assertCategory(memoryCategoryCheck{db: f.db, memID: memID, want: "preference"})

	// Equal confidence: lexicographic label ASC (behavioral < factual < preference).
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, `
			UPDATE ibex_core.memory_labels SET confidence = 0.80
			WHERE memory_id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("equalize confidence: %v", err)
	}
	f.mustInsertLabel(memoryLabelWrite{memID: memID, orgID: orgA, label: "behavioral", confidence: 0.80})
	f.assertCategory(memoryCategoryCheck{db: f.db, memID: memID, want: "behavioral"})
}

func TestMemoryLabels_Checks(t *testing.T) {
	f := openMigratedLabelsDB(t)
	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentID := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	memID := f.insertMemory(memoryWithCategory{
		orgID: orgA, agentID: agentID, content: "check mem", category: "factual", tokens: 1,
	})

	f.assertReject(f.insertLabel(memoryLabelWrite{
		memID: memID, orgID: orgA, label: "not-a-label", confidence: 1.0,
	}), sqlStateExpect{code: "23514"})
	f.assertReject(f.insertLabel(memoryLabelWrite{
		memID: memID, orgID: orgA, label: "factual", confidence: 1.5,
	}), sqlStateExpect{code: "23514"})
}

func TestRLSMemoryLabelsIsolation(t *testing.T) {
	f := openMigratedLabelsDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	seedLabeledMemory(t, f.ctx, labeledMemorySeed{
		db: f.db, orgID: orgA, agentSlug: "agent-a", content: "a-mem", label: "factual",
	})
	seedLabeledMemory(t, f.ctx, labeledMemorySeed{
		db: f.db, orgID: orgB, agentSlug: "agent-b", content: "b-mem", label: "preference",
	})

	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "memory_labels", orgID: "", want: 0})
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "memory_labels", orgID: orgA, want: 1})
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "memory_labels", orgID: orgB, want: 1})

	var serviceCount int
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, `SELECT COUNT(*) FROM ibex_core.memory_labels`).Scan(&serviceCount)
	})
	if err != nil {
		t.Fatalf("service count: %v", err)
	}
	if serviceCount != 2 {
		t.Fatalf("expected service count 2, got %d", serviceCount)
	}
}

func TestMemoryLabels_CascadeAndEmptyLeavesCategory(t *testing.T) {
	f := openMigratedLabelsDB(t)
	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	memID := seedLabeledMemory(t, f.ctx, labeledMemorySeed{
		db: f.db, orgID: orgA, agentSlug: "agent-a", content: "cascade-mem", label: "procedural",
	})
	f.assertCategory(memoryCategoryCheck{db: f.db, memID: memID, want: "procedural"})

	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, `
			DELETE FROM ibex_core.memory_labels WHERE memory_id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("delete labels: %v", err)
	}
	f.assertCategory(memoryCategoryCheck{db: f.db, memID: memID, want: "procedural"})

	err = withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, `DELETE FROM ibex_core.memories WHERE id = $1::uuid`, memID)
		return err
	})
	if err != nil {
		t.Fatalf("delete memory: %v", err)
	}

	var n int
	err = withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, `
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
	f := openMigratedLabelsDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	memA := seedLabeledMemory(t, f.ctx, labeledMemorySeed{
		db: f.db, orgID: orgA, agentSlug: "agent-a", content: "fk-mem", label: "factual",
	})
	f.assertReject(f.insertLabel(memoryLabelWrite{
		memID: memA, orgID: orgB, label: "preference", confidence: 1.0,
	}), sqlStateExpect{code: "23503"})
}

type memoryCategoryCheck struct {
	db    *sql.DB
	memID string
	want  string
}

func assertMemoryCategory(t *testing.T, ctx context.Context, check memoryCategoryCheck) {
	t.Helper()
	var got string
	err := withServiceAccount(ctx, check.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT category FROM ibex_core.memories WHERE id = $1::uuid`, check.memID).Scan(&got)
	})
	if err != nil {
		t.Fatalf("select category: %v", err)
	}
	if got != check.want {
		t.Fatalf("category=%q, want %q", got, check.want)
	}
}

func assertPQCode(t *testing.T, err error, want sqlStateExpect) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected SQLSTATE %s, got nil", want.code)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) || string(pqErr.Code) != want.code {
		t.Fatalf("expected SQLSTATE %s, got %v", want.code, err)
	}
}

type labeledMemorySeed struct {
	db                               *sql.DB
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
