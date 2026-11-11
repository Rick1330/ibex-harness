//go:build integration

package postgres

import (
	"strings"
	"testing"
)

// precheckFloor is the last migration before the unique prefix index pair
// (000070 precheck, 000071 index).
const precheckFloor = 69

// TestTenancyTokenPrefixPrecheckRefusesDuplicates proves 000070 stops a
// duplicate-prefix table before 000071 tries to build the index.
//
// This is the case the precheck exists for: a cluster that already carries two
// tenants on one prefix. `CREATE UNIQUE INDEX ... IF NOT EXISTS` would fail with
// a bare duplicate-key line, or silently accept an INVALID index left by an
// interrupted build, so the migration must refuse with a message that names the
// rows and the repair.
func TestTenancyTokenPrefixPrecheckRefusesDuplicates(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	// The refused migration leaves schema_migrations dirty at 000070 on purpose.
	// Reset on exit so the next package's `migrate up` starts from an empty
	// database instead of inheriting this test's deliberate failure.
	t.Cleanup(func() { resetSchema(t, f.db) })
	rewindBelowPrefixIndex(t, f)
	f.assertVersion(ctx, versionCheck{want: precheckFloor})

	holder := f.seedTenantNamed(ctx, "duplicate-holder")
	taker := f.seedTenantNamed(ctx, "duplicate-taker")
	f.seedTokenFor(ctx, holder.orgID, tokenSeed{prefix: "ibex_pat_duplicate", hash: "hash-dup-holder"})
	f.seedTokenFor(ctx, taker.orgID, tokenSeed{prefix: "ibex_pat_duplicate", hash: "hash-dup-taker"})

	err := Up(f.dsn)
	if err == nil {
		t.Fatal("expected the prefix precheck to refuse the duplicate prefix")
	}
	for _, want := range []string{
		"tokens.prefix must be unique",
		"ibex_pat_duplicate",
		"more than one organization",
		"delete the others",
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("precheck error does not contain %q: %v", want, err)
		}
	}
	// The repair must not suggest revocation: a revoked row keeps its prefix,
	// so the unique index would still refuse to build and the operator would
	// follow the instruction into the same failure.
	if strings.Contains(err.Error(), "revoke or delete") {
		t.Fatalf("repair guidance still offers revocation: %v", err)
	}
	if f.indexExists(ctx, indexName{qualified: "ibex_core.idx_tokens_prefix_unique"}) {
		t.Fatal("idx_tokens_prefix_unique exists after the refused migration")
	}
}

// rewindBelowPrefixIndex rolls the suite back to precheckFloor.
func rewindBelowPrefixIndex(t *testing.T, f *tenancyFixture) {
	t.Helper()
	rewindTo(t, f, precheckFloor)
}

// TestTenancyTokenPrefixPrecheckRefusesWrongShape proves 000070 refuses a
// relation that 000071 would otherwise accept by name alone.
//
// `CREATE UNIQUE INDEX ... IF NOT EXISTS` resolves its name against pg_class,
// so a table wearing the index name makes 000071 skip with a NOTICE and the
// invariant stays unenforced. A unique index over (hash) or (prefix, org_id) is
// a real index but does not make one prefix unique across organizations. Both
// are refused by name instead of reported as success.
func TestTenancyTokenPrefixPrecheckRefusesWrongShape(t *testing.T) {
	cases := []struct {
		name string
		ddl  string
		want string
	}{
		{
			name: "table wearing the index name",
			ddl:  `CREATE TABLE ibex_core.idx_tokens_prefix_unique (x int)`,
			want: "is not an index",
		},
		{
			name: "unique index on another column",
			ddl:  `CREATE UNIQUE INDEX idx_tokens_prefix_unique ON ibex_core.tokens (hash)`,
			want: "does not index exactly ibex_core.tokens (prefix)",
		},
		{
			name: "unique index on prefix and org_id",
			ddl:  `CREATE UNIQUE INDEX idx_tokens_prefix_unique ON ibex_core.tokens (prefix, org_id)`,
			want: "does not index exactly ibex_core.tokens (prefix)",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := newTenancyFixture(t)
			t.Cleanup(func() { resetSchema(t, f.db) })
			rewindTo(t, f, precheckFloor)
			f.exec(t.Context(), tc.ddl)
			err := Up(f.dsn)
			if err == nil {
				t.Fatalf("expected 000070 to refuse %s", tc.name)
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("precheck error does not contain %q: %v", tc.want, err)
			}
			if !strings.Contains(err.Error(), "idx_tokens_prefix_unique") {
				t.Fatalf("precheck error does not name the relation: %v", err)
			}
		})
	}
}
