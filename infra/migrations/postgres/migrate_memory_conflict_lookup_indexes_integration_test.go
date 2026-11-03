//go:build integration

package postgres

import (
	"context"
	"strings"
	"testing"
)

// The read path resolves the pending escalations a hydrated memory belongs to
// from both sides of the pair, so both partial indexes must exist with the
// expected keys and predicate. Assert the ordered keys, not only the names.
func TestMemoryConflictLookupIndexesExist(t *testing.T) {
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
			name: "idx_memory_conflict_escalations_org_new_pending",
			want: "ON ibex_core.memory_conflict_escalations USING btree (org_id, new_memory_id) WHERE (status = 'pending'::ibex_core.memory_conflict_escalation_status)",
		},
		{
			name: "idx_memory_conflict_escalations_org_candidate_pending",
			want: "ON ibex_core.memory_conflict_escalations USING btree (org_id, candidate_memory_id) WHERE (status = 'pending'::ibex_core.memory_conflict_escalation_status)",
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
