//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"
)

// The operator read models depend on the exact shape of these indexes: the
// ordered keys give the keyset page its sort order, and the partial predicate
// keeps the scan on the live rows. Asserting the name alone would still pass
// after a column, the order, or the predicate was dropped, which is the
// regression this test exists to catch.
func TestOperatorReadIndexesExist(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	for _, tc := range []struct {
		name string
		want string
	}{
		{
			name: "idx_memories_org_created_at",
			want: "ON ibex_core.memories USING btree (org_id, created_at DESC, id DESC)",
		},
		{
			name: "idx_sessions_org_created_at",
			want: "ON ibex_core.sessions USING btree (org_id, created_at DESC, id DESC) WHERE (deleted_at IS NULL)",
		},
		{
			name: "idx_evidence_runs_org_checkpoint",
			want: "ON ibex_core.evidence_runs USING btree (org_id, checkpoint_id) WHERE (checkpoint_id IS NOT NULL)",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			definition, err := indexDefinition(ctx, db, tc.name)
			if err != nil {
				t.Fatalf("read index %s: %v", tc.name, err)
			}
			if definition == "" {
				t.Fatalf("index %s is missing", tc.name)
			}
			if !strings.Contains(definition, tc.want) {
				t.Fatalf("index %s has the wrong shape\nwant definition containing: %s\ngot: %s",
					tc.name, tc.want, definition)
			}
		})
	}
}

func indexDefinition(ctx context.Context, db *sql.DB, name string) (string, error) {
	var definition string
	err := db.QueryRowContext(ctx, `
		SELECT pg_get_indexdef(c.oid)
		  FROM pg_class c
		  JOIN pg_namespace n ON n.oid = c.relnamespace
		 WHERE n.nspname = 'ibex_core'
		   AND c.relname = $1`, name).Scan(&definition)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return definition, nil
}
