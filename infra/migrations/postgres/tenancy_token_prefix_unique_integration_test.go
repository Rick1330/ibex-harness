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
	} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("precheck error does not contain %q: %v", want, err)
		}
	}
	if f.indexExists(ctx, indexName{qualified: "ibex_core.idx_tokens_prefix_unique"}) {
		t.Fatal("idx_tokens_prefix_unique exists after the refused migration")
	}
}

// rewindBelowPrefixIndex rolls the suite back to precheckFloor.
func rewindBelowPrefixIndex(t *testing.T, f *tenancyFixture) {
	t.Helper()
	for version := maxEmbeddedMigrationVersion(t); version > precheckFloor; version-- {
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down from %d: %v", version, err)
		}
	}
}
