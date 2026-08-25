//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/lib/pq"
)

const insertMemoryMinimalRelSQL = `
	INSERT INTO ibex_core.memories (
		org_id, agent_id, content, content_hash, content_tokens, category
	) VALUES (
		$1::uuid, $2::uuid, $3, $4, 1, 'factual'
	)
	RETURNING id::text`

const insertRelationshipSQL = `
	INSERT INTO ibex_core.memory_relationships (
		org_id, source_memory_id, target_memory_id, relationship_type, confidence
	) VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5)`

type relationshipsDB struct {
	t   *testing.T
	db  *sql.DB
	ctx context.Context
}

type relationshipWrite struct {
	orgID, sourceID, targetID, relType string
	confidence                         float64
}

type relationshipMemorySeed struct {
	orgID, agentID, content string
}

func openMigratedRelationshipsDB(t *testing.T) *relationshipsDB {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		db.Close()
		t.Fatalf("up: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return &relationshipsDB{t: t, db: db, ctx: context.Background()}
}

func (f *relationshipsDB) insertMemory(seed relationshipMemorySeed) string {
	f.t.Helper()
	var memID string
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, insertMemoryMinimalRelSQL,
			seed.orgID, seed.agentID, seed.content, "hash-"+seed.content,
		).Scan(&memID)
	})
	if err != nil {
		f.t.Fatalf("insert memory: %v", err)
	}
	return memID
}

func (f *relationshipsDB) insertEdge(w relationshipWrite) error {
	f.t.Helper()
	return withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, insertRelationshipSQL,
			w.orgID, w.sourceID, w.targetID, w.relType, w.confidence)
		return err
	})
}

func (f *relationshipsDB) mustInsertEdge(w relationshipWrite) {
	f.t.Helper()
	if err := f.insertEdge(w); err != nil {
		f.t.Fatalf("insert edge %s: %v", w.relType, err)
	}
}

func (f *relationshipsDB) assertReject(err error, want sqlStateExpect) {
	f.t.Helper()
	assertPQCode(f.t, err, want)
}

func (f *relationshipsDB) resolveTip(orgID, memID string, maxDepth int) string {
	f.t.Helper()
	var tip string
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, `
			SELECT ibex_core.resolve_supersession_tip($1::uuid, $2::uuid, $3)::text`,
			orgID, memID, maxDepth).Scan(&tip)
	})
	if err != nil {
		f.t.Fatalf("resolve tip: %v", err)
	}
	return tip
}

func TestMemoryRelationships_TableForceRLSAndView(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	assertCoreTableExists(t, f.ctx, f.db, "memory_relationships")
	assertCoreTableRLS(t, f.ctx, coreTableRLSCheck{
		db: f.db, table: "memory_relationships", expect: coreTableRLSFlags{forced: true},
	})

	var viewExists bool
	err := f.db.QueryRowContext(f.ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.views
			WHERE table_schema = 'ibex_core' AND table_name = 'memory_supersession_edges'
		)`).Scan(&viewExists)
	if err != nil {
		t.Fatalf("check view: %v", err)
	}
	if !viewExists {
		t.Fatal("missing view ibex_core.memory_supersession_edges")
	}

	var reloptions pq.StringArray
	err = f.db.QueryRowContext(f.ctx, `
		SELECT c.reloptions
		FROM pg_class c
		JOIN pg_namespace n ON n.oid = c.relnamespace
		WHERE n.nspname = 'ibex_core' AND c.relname = 'memory_supersession_edges'`,
	).Scan(&reloptions)
	if err != nil {
		t.Fatalf("view reloptions: %v", err)
	}
	if !containsString([]string(reloptions), "security_invoker=true") {
		t.Fatalf("expected security_invoker=true, got %v", reloptions)
	}
}

func TestMemoryRelationships_IndexesPresentAndUsed(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	assertIndexExists(t, f.ctx, f.db, "idx_memory_relationships_org_source_type")
	assertIndexExists(t, f.ctx, f.db, "idx_memory_relationships_org_target_type")

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentID := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	older := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "older"})
	newer := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "newer"})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: newer, targetID: older, relType: "supersedes", confidence: 0.95,
	})

	assertExplainUsesIndex(t, f.ctx, explainIndexCheck{
		db: f.db, indexName: "idx_memory_relationships_org_source_type",
		query: `
			SELECT source_memory_id FROM ibex_core.memory_relationships
			WHERE org_id = $1::uuid AND source_memory_id = $2::uuid
			  AND relationship_type = 'supersedes'`,
		arg1: orgA, arg2: newer,
	})
	assertExplainUsesIndex(t, f.ctx, explainIndexCheck{
		db: f.db, indexName: "idx_memory_relationships_org_target_type",
		query: `
			SELECT source_memory_id FROM ibex_core.memory_relationships
			WHERE org_id = $1::uuid AND target_memory_id = $2::uuid
			  AND relationship_type = 'supersedes'`,
		arg1: orgA, arg2: older,
	})
}

func TestMemoryRelationships_ChecksAndUnique(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentID := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	a := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "mem-a"})
	b := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "mem-b"})

	f.assertReject(f.insertEdge(relationshipWrite{
		orgID: orgA, sourceID: a, targetID: b, relType: "not-a-type", confidence: 0.9,
	}), sqlStateExpect{code: "23514"})
	f.assertReject(f.insertEdge(relationshipWrite{
		orgID: orgA, sourceID: a, targetID: b, relType: "supersedes", confidence: 1.5,
	}), sqlStateExpect{code: "23514"})
	f.assertReject(f.insertEdge(relationshipWrite{
		orgID: orgA, sourceID: a, targetID: a, relType: "supersedes", confidence: 0.9,
	}), sqlStateExpect{code: "23514"})

	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: a, targetID: b, relType: "supersedes", confidence: 0.9,
	})
	f.assertReject(f.insertEdge(relationshipWrite{
		orgID: orgA, sourceID: a, targetID: b, relType: "supersedes", confidence: 0.8,
	}), sqlStateExpect{code: "23505"})
}

func TestMemoryRelationships_CrossOrgFKRejected(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentA := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	agentB := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgB, slug: "agent-b"})
	memA := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "a"})
	memB := f.insertMemory(relationshipMemorySeed{orgID: orgB, agentID: agentB, content: "b"})

	f.assertReject(f.insertEdge(relationshipWrite{
		orgID: orgA, sourceID: memA, targetID: memB, relType: "supersedes", confidence: 0.9,
	}), sqlStateExpect{code: "23503"})
}

func TestRLSMemoryRelationshipsIsolation(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentA := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	agentB := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgB, slug: "agent-b"})

	a1 := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "a1"})
	a2 := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "a2"})
	b1 := f.insertMemory(relationshipMemorySeed{orgID: orgB, agentID: agentB, content: "b1"})
	b2 := f.insertMemory(relationshipMemorySeed{orgID: orgB, agentID: agentB, content: "b2"})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: a2, targetID: a1, relType: "supersedes", confidence: 0.9,
	})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgB, sourceID: b2, targetID: b1, relType: "contradicts", confidence: 0.7,
	})

	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "memory_relationships", orgID: "", want: 0})
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "memory_relationships", orgID: orgA, want: 1})
	assertTableCount(t, f.ctx, tableCountCheck{db: f.db, table: "memory_relationships", orgID: orgB, want: 1})
}

func TestMemoryRelationships_CascadeAndViewFilter(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentID := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	older := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "old"})
	newer := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "new"})
	other := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentID, content: "other"})

	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: newer, targetID: older, relType: "supersedes", confidence: 0.9,
	})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: other, targetID: older, relType: "contradicts", confidence: 0.5,
	})

	var supersedeCount, allCount int
	err := withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(f.ctx, `
			SELECT COUNT(*) FROM ibex_core.memory_supersession_edges`).Scan(&supersedeCount); err != nil {
			return err
		}
		return tx.QueryRowContext(f.ctx, `
			SELECT COUNT(*) FROM ibex_core.memory_relationships`).Scan(&allCount)
	})
	if err != nil {
		t.Fatalf("view counts: %v", err)
	}
	if supersedeCount != 1 || allCount != 2 {
		t.Fatalf("view=%d all=%d, want view=1 all=2", supersedeCount, allCount)
	}

	err = withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, `DELETE FROM ibex_core.memories WHERE id = $1::uuid`, older)
		return err
	})
	if err != nil {
		t.Fatalf("delete memory: %v", err)
	}

	var remaining int
	err = withServiceAccount(f.ctx, f.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(f.ctx, `
			SELECT COUNT(*) FROM ibex_core.memory_relationships
			WHERE source_memory_id = $1::uuid OR target_memory_id = $1::uuid`, older,
		).Scan(&remaining)
	})
	if err != nil {
		t.Fatalf("count after cascade: %v", err)
	}
	if remaining != 0 {
		t.Fatalf("expected 0 edges after cascade, got %d", remaining)
	}
}

func TestMemoryRelationships_ResolveTipChainCycleAndEmpty(t *testing.T) {
	f := openMigratedRelationshipsDB(t)
	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	agentA := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgA, slug: "agent-a"})
	agentB := lookupAgentID(t, f.ctx, agentLookup{db: f.db, orgID: orgB, slug: "agent-b"})

	b := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "b"})
	a := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "a"})
	c := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "c"})
	lonely := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "lonely"})

	// C supersedes A supersedes B → tip from B is C.
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: a, targetID: b, relType: "supersedes", confidence: 0.9,
	})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: c, targetID: a, relType: "supersedes", confidence: 0.95,
	})

	if tip := f.resolveTip(orgA, b, 5); tip != c {
		t.Fatalf("chain tip from B=%s, want C=%s", tip, c)
	}
	if tip := f.resolveTip(orgA, lonely, 5); tip != lonely {
		t.Fatalf("empty tip=%s, want start %s", tip, lonely)
	}

	// Isolated cycle Y ↔ Z: depth cap / path guard must terminate (not on B→A→C).
	y := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "y"})
	z := f.insertMemory(relationshipMemorySeed{orgID: orgA, agentID: agentA, content: "z"})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: y, targetID: z, relType: "supersedes", confidence: 0.9,
	})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgA, sourceID: z, targetID: y, relType: "supersedes", confidence: 0.9,
	})
	_ = f.resolveTip(orgA, y, 5)

	// Org filters stay isolated across tenants.
	bMem := f.insertMemory(relationshipMemorySeed{orgID: orgB, agentID: agentB, content: "borg"})
	bTip := f.insertMemory(relationshipMemorySeed{orgID: orgB, agentID: agentB, content: "btip"})
	f.mustInsertEdge(relationshipWrite{
		orgID: orgB, sourceID: bTip, targetID: bMem, relType: "supersedes", confidence: 0.9,
	})
	if tip := f.resolveTip(orgB, bMem, 5); tip != bTip {
		t.Fatalf("orgB tip=%s, want %s", tip, bTip)
	}
	if tip := f.resolveTip(orgA, b, 5); tip != c {
		t.Fatalf("orgA tip polluted: got %s want %s", tip, c)
	}
}

type explainIndexCheck struct {
	db               *sql.DB
	query, indexName string
	arg1, arg2       string
}

func assertIndexExists(t *testing.T, ctx context.Context, db *sql.DB, name string) {
	t.Helper()
	var exists bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM pg_indexes
			WHERE schemaname = 'ibex_core' AND indexname = $1
		)`, name).Scan(&exists)
	if err != nil {
		t.Fatalf("check index %s: %v", name, err)
	}
	if !exists {
		t.Fatalf("missing index %s", name)
	}
}

func assertExplainUsesIndex(t *testing.T, ctx context.Context, check explainIndexCheck) {
	t.Helper()
	var plans []string
	err := withServiceAccount(ctx, check.db, func(tx *sql.Tx) error {
		rows, err := tx.QueryContext(ctx, `EXPLAIN `+check.query, check.arg1, check.arg2)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var line string
			if err := rows.Scan(&line); err != nil {
				return err
			}
			plans = append(plans, line)
		}
		return rows.Err()
	})
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	joined := strings.Join(plans, "\n")
	if !strings.Contains(joined, check.indexName) {
		t.Fatalf("expected EXPLAIN to mention %s, got:\n%s", check.indexName, joined)
	}
}

func containsString(hay []string, needle string) bool {
	for _, h := range hay {
		if h == needle {
			return true
		}
	}
	return false
}
