//go:build integration

package postgres

import (
	"context"
	"testing"
)

func TestOperatorReadIndexesExist(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	for _, name := range []string{
		"idx_memories_org_created_at",
		"idx_sessions_org_created_at",
		"idx_evidence_runs_org_checkpoint",
	} {
		var exists bool
		err := db.QueryRowContext(ctx, `
			SELECT EXISTS (
				SELECT 1
				  FROM pg_indexes
				 WHERE schemaname = 'ibex_core'
				   AND indexname = $1
			)`, name).Scan(&exists)
		if err != nil {
			t.Fatalf("query index %s: %v", name, err)
		}
		if !exists {
			t.Errorf("index %s is missing", name)
		}
	}
}
