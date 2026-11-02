//go:build integration

package postgres

import (
	"context"
	"strings"
	"testing"
)

// The directive list pages by (updated_at, id) inside an org, and the detail
// counts sessions per directive version inside a window. Assert the ordered
// keys, not only the names.
func TestDirectiveUsageIndexesExist(t *testing.T) {
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
			name: "idx_directives_org_updated_at",
			want: "ON ibex_core.directives USING btree (org_id, updated_at DESC, id DESC)",
		},
		{
			name: "idx_sessions_org_directive_created",
			want: "ON ibex_core.sessions USING btree (org_id, directive_version_id, created_at DESC) WHERE (directive_version_id IS NOT NULL)",
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
