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
	assertVectorExtension(t, ctx, db, true)
	assertHNSWIndex(t, ctx, db)
	assertIndexesExist(t, ctx, db, []string{"idx_memories_validity", "idx_memories_search_vector"})
}

func TestMemorySchemaV2_QualityDefaultsAndSearchVector(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	memID := seedMemory(t, ctx, memorySeed{db: db, orgID: orgA, agentSlug: "agent-a", content: "quality defaults"})
	assertMemoryQualityDefaults(t, ctx, db, memID)
}

func TestMemorySchemaV2_EmbeddingTripletAndChecks(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})
	vec := zeroEmbedding1024()

	memID := insertMemoryWithEmbedding(t, ctx, db, orgA, agentID, vec)
	if memID == "" {
		t.Fatal("expected memory id")
	}

	assertPQCode(t, execAsService(t, ctx, db, `
		INSERT INTO ibex_core.memories (
			org_id, agent_id, content, content_hash, content_tokens, embedding
		) VALUES ($1::uuid, $2::uuid, 'bad triplet', 'hash-emb-bad', 1, $3::vector)`,
		orgA, agentID, vec), sqlStateExpect{code: "23514"})

	assertPQCode(t, execAsService(t, ctx, db,
		`UPDATE ibex_core.memories SET confidence = 1.5 WHERE id = $1::uuid`, memID),
		sqlStateExpect{code: "23514"})
	assertPQCode(t, execAsService(t, ctx, db,
		`UPDATE ibex_core.memories SET usefulness_score = -0.1 WHERE id = $1::uuid`, memID),
		sqlStateExpect{code: "23514"})
	assertPQCode(t, execAsService(t, ctx, db,
		`UPDATE ibex_core.memories SET source = 'not-a-source' WHERE id = $1::uuid`, memID),
		sqlStateExpect{code: "23514"})
}

func TestMemorySchemaV2_EmbeddingModelAndMetadataBounds(t *testing.T) {
	db, _ := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	orgA, _ := seedTwoOrgsWithAgents(t, ctx, db)
	agentID := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})
	vec := zeroEmbedding1024()
	memID := insertMemoryWithEmbedding(t, ctx, db, orgA, agentID, vec)

	// Valid metadata object write.
	if err := execAsService(t, ctx, db,
		`UPDATE ibex_core.memories SET metadata = '{"k":"v"}'::jsonb WHERE id = $1::uuid`, memID); err != nil {
		t.Fatalf("valid metadata object: %v", err)
	}

	oversizedModel := strings.Repeat("m", 257)
	assertPQCode(t, execAsService(t, ctx, db, `
		UPDATE ibex_core.memories
		SET embedding_model = $1
		WHERE id = $2::uuid`, oversizedModel, memID), sqlStateExpect{code: "23514"})

	assertPQCode(t, execAsService(t, ctx, db,
		`UPDATE ibex_core.memories SET metadata = '["not","object"]'::jsonb WHERE id = $1::uuid`, memID),
		sqlStateExpect{code: "23514"})

	oversizedMeta := `{"pad":"` + strings.Repeat("x", 8200) + `"}`
	assertPQCode(t, execAsService(t, ctx, db,
		`UPDATE ibex_core.memories SET metadata = $1::jsonb WHERE id = $2::uuid`, oversizedMeta, memID),
		sqlStateExpect{code: "23514"})
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
	assertMigrationVersionAtLeast(t, dsn, 17)
}

func TestMemorySchemaV2_DownRemovesExpandColumns(t *testing.T) {
	db, dsn := openMigratedSchemaV2DB(t)
	ctx := context.Background()
	downToVersion(t, dsn, 16)
	assertColumnPresent(t, ctx, db, "embedding", false)
	assertColumnPresent(t, ctx, db, "observed_at", true)
	assertVectorExtension(t, ctx, db, true)
}

func assertVectorExtension(t *testing.T, ctx context.Context, db *sql.DB, want bool) {
	t.Helper()
	var exists bool
	if err := db.QueryRowContext(ctx,
		`SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')`).Scan(&exists); err != nil {
		t.Fatalf("vector extension check: %v", err)
	}
	if exists != want {
		t.Fatalf("vector extension exists=%v, want %v", exists, want)
	}
}

func assertHNSWIndex(t *testing.T, ctx context.Context, db *sql.DB) {
	t.Helper()
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
}

func assertIndexesExist(t *testing.T, ctx context.Context, db *sql.DB, indexes []string) {
	t.Helper()
	for _, idx := range indexes {
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

func assertMemoryQualityDefaults(t *testing.T, ctx context.Context, db *sql.DB, memID string) {
	t.Helper()
	var (
		confidence, usefulness   float64
		source                   string
		retrievalCount           int
		piiDetected, piiRedacted bool
		metadata                 string
		searchVec                sql.NullString
		embeddingNull            bool
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
	if confidence != 0.80 {
		t.Fatalf("confidence=%v, want 0.80", confidence)
	}
	if usefulness != 0.50 {
		t.Fatalf("usefulness=%v, want 0.50", usefulness)
	}
	if source != "extracted" {
		t.Fatalf("source=%q, want extracted", source)
	}
	if retrievalCount != 0 {
		t.Fatalf("retrieval_count=%d, want 0", retrievalCount)
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

func insertMemoryWithEmbedding(t *testing.T, ctx context.Context, db *sql.DB, orgID, agentID, vec string) string {
	t.Helper()
	var memID string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.memories (
				org_id, agent_id, content, content_hash, content_tokens,
				embedding, embedding_model, embedding_dim
			) VALUES (
				$1::uuid, $2::uuid, 'embedded mem', 'hash-emb-1', 2,
				$3::vector, 'bge-m3', 1024
			) RETURNING id::text`, orgID, agentID, vec).Scan(&memID)
	})
	if err != nil {
		t.Fatalf("insert with embedding: %v", err)
	}
	return memID
}

func execAsService(t *testing.T, ctx context.Context, db *sql.DB, query string, args ...any) error {
	t.Helper()
	return withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, query, args...)
		return err
	})
}

func assertMigrationVersionAtLeast(t *testing.T, dsn string, min uint) {
	t.Helper()
	v, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatal("expected clean migration state")
	}
	if v < min {
		t.Fatalf("expected version >= %d, got %d", min, v)
	}
}

func downToVersion(t *testing.T, dsn string, want uint) {
	t.Helper()
	for {
		v, dirty, err := Version(dsn)
		if err != nil {
			t.Fatalf("version: %v", err)
		}
		if dirty {
			t.Fatalf("dirty at v=%d", v)
		}
		if v == want {
			return
		}
		if err := Down(dsn); err != nil {
			t.Fatalf("down from %d: %v", v, err)
		}
	}
}

func assertColumnPresent(t *testing.T, ctx context.Context, db *sql.DB, column string, want bool) {
	t.Helper()
	var exists bool
	err := db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM information_schema.columns
			WHERE table_schema = 'ibex_core'
			  AND table_name = 'memories'
			  AND column_name = $1
		)`, column).Scan(&exists)
	if err != nil {
		t.Fatalf("column %s check: %v", column, err)
	}
	if exists != want {
		t.Fatalf("column %s exists=%v, want %v", column, exists, want)
	}
}
