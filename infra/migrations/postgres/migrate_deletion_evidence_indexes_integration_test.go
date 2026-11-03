//go:build integration

package postgres

import (
	"context"
	"strings"
	"testing"
)

// The deletion-evidence read filters lifecycle events by org and window, and
// counts the tombstone fence. Assert the ordered keys, not only the names.
func TestDeletionEvidenceIndexesExist(t *testing.T) {
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
			name: "idx_memory_lifecycle_outbox_org_occurred",
			want: "ON ibex_core.memory_lifecycle_outbox USING btree (org_id, occurred_at DESC)",
		},
		{
			name: "idx_memories_org_tombstoned",
			want: "ON ibex_core.memories USING btree (org_id) WHERE tombstoned",
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
