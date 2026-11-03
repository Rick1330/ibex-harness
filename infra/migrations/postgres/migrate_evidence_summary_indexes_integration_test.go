//go:build integration

package postgres

import (
	"context"
	"strings"
	"testing"
)

// The evidence summary filters both tables by organization and row age, so the
// ordered keys have to exist. Asserting the name alone would still pass after a
// column or the order changed, which is the regression this guards.
func TestEvidenceSummaryIndexesExist(t *testing.T) {
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
			name: "idx_evidence_runs_org_started_at",
			want: "ON ibex_core.evidence_runs USING btree (org_id, started_at DESC)",
		},
		{
			name: "idx_evidence_outbox_org_created_at",
			want: "ON ibex_core.evidence_outbox USING btree (org_id, created_at DESC)",
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
