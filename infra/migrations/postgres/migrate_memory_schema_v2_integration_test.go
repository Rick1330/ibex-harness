//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"
)

func openMigratedSchemaV2DB(t *testing.T) (*sql.DB, string) {
	t.Helper()
	dsn := testDSN()
	db := openTestDB(t)
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		db.Close()
		t.Fatalf("up: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db, dsn
}

func zeroEmbedding1024() string {
	parts := make([]string, 1024)
	for i := range parts {
		parts[i] = "0"
	}
	return "[" + strings.Join(parts, ",") + "]"
}

func TestMemorySchemaV2_ExtensionAndHNSWIndex(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()

	var extExists bool
	if err := db.QueryRowContext(ctx, `
		SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')`).Scan(&extExists); err != nil {
		t.Fatalf("vector extension check: %v", err)
	}
	if !extExists {
		t.Fatal("expected pgvector extension to be installed")
	}

	var amName string
	err := db.QueryRowContext(ctx, `
		SELECT a.amname
		FROM pg_class c
		JOIN pg_namespace n ON n.oid = c.relnamespace
		JOIN pg_am a ON a.oid = c.relam
		WHERE n.nspname = 'ibex_core'
		  AND c.relname = 'idx_memories_embedding_hnsw'
		  AND c.relkind = 'i'`).Scan(&amName)
	if err != nil {
		t.Fatalf("hnsw index catalog lookup: %v", err)
	}
	if amName != "hnsw" {
		t.Fatalf("idx_memories_embedding_hnsw amname=%q, want hnsw", amName)
	}

	for _, idx := range []string{"idx_memories_validity", "idx_memories_search_vector"} {
		var exists bool
		if err := db.QueryRowContext(ctx, `
			SELECT EXISTS (
				SELECT 1 FROM pg_indexes
				WHERE schemaname = 'ibex_core' AND indexname = $1
			)`, idx).Scan(&exists); err != nil {
			t.Fatalf("index %s exists check: %v", idx, err)
		}
		if !exists {
			t.Fatalf("missing index %s", idx)
		}
	}
}

func TestMemorySchemaV2_QualityDefaultsAndSearchVector(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memID := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "quality defaults"})

	var (
		confidence, usefulness float64
		source                 string
		retrievalCount         int
		piiDetected, piiRedacted bool
		metadata               string
		searchVec              sql.NullString
		embeddingNull          bool
	)
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			SELECT confidence::float8, usefulness_score::float8, source, retrieval_count,
			       pii_detected, pii_redacted, metadata::text,
			       search_vector::text, (embedding IS NULL)
			FROM ibex_core.memories WHERE id = $1::uuid`, memID).Scan(
			&confidence, &usefulness, &source, &retrievalCount,
			&piiDetected, &piiRedacted, &metadata,
			&searchVec, &embeddingNull,
		)
	})
	if err != nil {
		t.Fatalf("select quality columns: %v", err)
	}
	if confidence != 0.80 || usefulness != 0.50 || source != "extracted" || retrievalCount != 0 {
		t.Fatalf("unexpected defaults confidence=%v usefulness=%v source=%q retrieval=%d",
			confidence, usefulness, source, retrievalCount)
	}
	if piiDetected || piiRedacted {
		t.Fatal("expected pii flags false")
	}
	if metadata != "{}" {
		t.Fatalf("metadata=%q, want {}", metadata)
	}
	if !embeddingNull {
		t.Fatal("expected embedding NULL without embed write")
	}
	if !searchVec.Valid || searchVec.String == "" {
		t.Fatal("expected generated search_vector")
	}
}

func TestMemorySchemaV2_EmbeddingTripletAndChecks(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})
	vec := zeroEmbedding1024()

	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				embedding, embedding_model, embedding_dim
			) VALUES (
				$1::uuid, $2::uuid, 'embedded mem', 'hash-emb-1', 2,
				$3::vector, 'bge-m3', 1024
			) RETURNING id::text`, orgA, agentID, vec).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert with embedding: %v", err)
	}
	if memID == "" {
		t.Fatal("expected memory id")
	}

	// Partial triplet (embedding without model) must fail CHECK.
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens, embedding
			) VALUES (
				$1::uuid, $2::uuid, 'bad triplet', 'hash-emb-bad', 1, $3::vector
			)`, orgA, agentID, vec)
		return err
	})
	assertPQCode(t, err, sqlStateExpect{code: "23514"})

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.memories SET confidence = 1.5 WHERE id = $1::uuid`, memID)
		return err
	})
	assertPQCode(t, err, sqlStateExpect{code: "23514"})

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.memories SET usefulness_score = -0.1 WHERE id = $1::uuid`, memID)
		return err
	})
	assertPQCode(t, err, sqlStateExpect{code: "23514"})

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			UPDATE ibex_core.memories SET source = 'not-a-source' WHERE id = $1::uuid`, memID)
		return err
	})
	assertPQCode(t, err, sqlStateExpect{code: "23514"})
}

func TestMemorySchemaV2_RLSIsolationStillHolds(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "v2-a"})
	seedMemory(t, ctx, memorySeed{db: db, orgID: orgB, agentSlug: "agent-b", content: "v2-b"})

	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "memories", orgID: orgB, want: 1})
	assertMemoriesForceRLS(t, ctx, db)
}

func TestMemorySchemaV2_PrimaryCategoryTriggerRegression(t *testing.T) {
	// Existing sync_memory_primary_category from 000015 must still win after expand.
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})

	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, insertMemoryWithCategorySQL,
			orgA, agentID, "trigger regression", "hash-trig", 2, "factual",
		).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert memory: %v", err)
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "factual", 0.40); err != nil {
			return err
		}
		_, err := tx.ExecContext(ctx, insertMemoryLabelSQL, memID, orgA, "preference", 0.95)
		return err
	})
	if err != nil {
		t.Fatalf("insert labels: %v", err)
	}
	assertMemoryCategory(t, ctx, memoryCategoryCheck{db: db, memID: memID, want: "preference"})
}

func TestMemorySchemaV2_MigrateUpIdempotentIncludesV17(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("first up: %v", err)
	}
	if err := Up(dsn); err != nil {
		t.Fatalf("second up: %v", err)
	}
	v, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatal("expected clean migration state")
	}
	if v < 17 {
		t.Fatalf("expected version >= 17, got %d", v)
	}
}

func TestMemorySchemaV2_DownRemovesExpandColumns(t *testing.T) {
	db, dsn := openMigratedSchemaV2DB(t)
	ctx := context.Background()

	for {
		v, dirty, err := Version(dsn)
		if err != nil {
			t.Fatalf("version: %v", err)
		}
		if dirty {
			t.Fatalf("dirty at v=%d", v)
		}
		if v == 16 {
			break
		}
		if err := Down(dsn); err != nil {
			t.Fatalf("down from %d: %v", v, err)
		}
	}

	var hasEmbedding bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.columns
			WHERE table_schema = 'ibex_core'
			  AND table_name = 'memories'
			  AND column_name = 'embedding'
		)`).Scan(&hasEmbedding)
	if err != nil {
		t.Fatalf("column check: %v", err)
	}
	if hasEmbedding {
		t.Fatal("expected embedding column removed after down to 16")
	}

	// Foundation columns from 000014 remain.
	var hasObservedAt bool
	err = db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.columns
			WHERE table_schema = 'ibex_core'
			  AND table_name = 'memories'
			  AND column_name = 'observed_at'
		)`).Scan(&hasObservedAt)
	if err != nil {
		t.Fatalf("observed_at check: %v", err)
	}
	if !hasObservedAt {
		t.Fatal("expected observed_at to remain after down to 16")
	}

	// Extension intentionally left installed.
	var extExists bool
	if err := db.QueryRowContext(ctx, `
		SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')`).Scan(&extExists); err != nil {
		t.Fatalf("extension after down: %v", err)
	}
	if !extExists {
		t.Fatal("expected vector extension to remain after down")
	}
}
