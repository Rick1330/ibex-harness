//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// 000072/000073 add the erasure provenance substrate: the refs that make a
// memory's external copies (object store, ClickHouse, session event) reachable,
// and the per-memory receipts that prove each store was cleared.
//
// Both are forward-only in production (ADR-0098). The down files exist for dev
// rollback and must refuse to run once a row exists, because dropping the table
// would destroy the only record that those copies belong to the memory.
const (
	memoryArtifactRefsVersion   = 72
	erasureStoreReceiptsVersion = 73
)

// provenanceTables are the two tables this pair of migrations owns.
var provenanceTables = []string{"memory_artifact_refs", "erasure_store_receipts"}

// TestErasureProvenance_UpDownUp drives the reversible range end to end: migrate
// to head, roll both files back with no rows present, and migrate up again.
//
// The rollback has to be proven here rather than in production: a down that only
// works on a fresh database is not a rollback plan, and a down that leaves a
// policy or trigger behind makes the next up fail instead of restoring the
// schema.
func TestErasureProvenance_UpDownUp(t *testing.T) {
	f := newMigrationFixture(t, erasureStoreReceiptsVersion)

	requireProvenanceTables(t, f.ctx, f.db, true)

	downToVersion(t, f.dsn, memoryArtifactRefsVersion-1)
	requireVersion(t, f.dsn, memoryArtifactRefsVersion-1)
	requireProvenanceTables(t, f.ctx, f.db, false)

	if err := Up(f.dsn); err != nil {
		t.Fatalf("re-up after clean down: %v", err)
	}
	requireVersion(t, f.dsn, f.head)
	requireProvenanceTables(t, f.ctx, f.db, true)
}

// TestErasureProvenance_DownRefusesAfterRowsExist pins the guard on both down
// files. The down SQL is executed inside a transaction that is rolled back, so
// the refusal is proven without leaving the database dirty or below head.
func TestErasureProvenance_DownRefusesAfterRowsExist(t *testing.T) {
	f := newMigrationFixture(t, erasureStoreReceiptsVersion)

	orgA, _ := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	insertArtifactRef(t, f.ctx, f.db, artifactRefSeed{
		orgID:    orgA,
		memoryID: uuid.NewString(),
		store:    "objectstore",
		locator:  "s3://ibex-sessions/" + orgA + "/capture/full/1.json",
	})
	insertErasureReceipt(t, f.ctx, f.db, erasureReceiptSeed{
		orgID:    orgA,
		memoryID: uuid.NewString(),
		revision: 2,
		store:    "objectstore",
	})

	for _, tc := range []downRefusal{
		{file: "000072_memory_artifact_refs.down.sql", message: "refusing destructive 000072 rollback"},
		{file: "000073_erasure_store_receipts.down.sql", message: "refusing destructive 000073 rollback"},
	} {
		t.Run(tc.file, func(t *testing.T) {
			requireDownRefused(t, f.ctx, f.db, tc)
		})
	}
	requireVersion(t, f.dsn, f.head)
}

// TestErasureProvenance_ShapeAndGrants asserts the properties the erasure path
// depends on: the read index, forced RLS through the 000063 helper, the tenant
// grants, and the deliberate absence of a foreign key.
func TestErasureProvenance_ShapeAndGrants(t *testing.T) {
	f := newMigrationFixture(t, erasureStoreReceiptsVersion)

	assertCoreTablesExist(t, f.ctx, f.db, provenanceTables)
	for _, table := range provenanceTables {
		assertCoreTableRLS(t, f.ctx, coreTableRLSCheck{
			db: f.db, table: table, expect: coreTableRLSFlags{enabled: true, forced: true},
		})
	}
	requireIndexShape(t, f.ctx, f.db, indexShape{
		name: "idx_memory_artifact_refs_org_memory",
		want: "ON ibex_core.memory_artifact_refs USING btree (org_id, memory_id)",
	})
	requireIndexShape(t, f.ctx, f.db, indexShape{
		name: "idx_erasure_store_receipts_org_memory",
		want: "ON ibex_core.erasure_store_receipts USING btree (org_id, memory_id)",
	})
	for _, table := range provenanceTables {
		requireOrgPolicy(t, f.ctx, f.db, table)
		requireNoForeignKey(t, f.ctx, f.db, table)
		requireTenantGrants(t, f.ctx, f.db, table)
	}
}

// TestErasureProvenance_RLSCrossTenant proves org A cannot read, count, or write
// org B's refs through the tenant role. The owner connection seeds; every
// assertion runs as ibex_app with app.current_org_id set, which is the identity
// the capture archiver and the erasure saga use.
func TestErasureProvenance_RLSCrossTenant(t *testing.T) {
	f := newMigrationFixture(t, erasureStoreReceiptsVersion)

	orgA, orgB := seedTwoOrgsWithAgents(t, f.ctx, f.db)
	memoryA, memoryB := uuid.NewString(), uuid.NewString()
	insertArtifactRef(t, f.ctx, f.db, artifactRefSeed{
		orgID: orgA, memoryID: memoryA, store: "objectstore", locator: "s3://bucket/a.json",
	})
	insertArtifactRef(t, f.ctx, f.db, artifactRefSeed{
		orgID: orgB, memoryID: memoryB, store: "objectstore", locator: "s3://bucket/b.json",
	})

	requireVisibleRefs(t, f.ctx, f.db, artifactScope{orgID: orgA, want: 1})
	requireVisibleRefs(t, f.ctx, f.db, artifactScope{orgID: orgB, want: 1})
	requireVisibleRefs(t, f.ctx, f.db, artifactScope{orgID: "", want: 0})

	requireAppInsert(t, f.ctx, f.db, appInsert{scope: artifactScope{orgID: orgA, otherOrgID: orgB, memoryID: memoryB}, org: orgB, wantErr: "42501"})
	requireAppInsert(t, f.ctx, f.db, appInsert{scope: artifactScope{orgID: orgA, memoryID: memoryA}, org: orgA})
	for _, table := range provenanceTables {
		requireAppDeleteRefused(t, f.ctx, f.db, deleteRefusal{table: table, orgID: orgA})
	}

	// The same (org, memory, store, locator) delivered twice is one row: the
	// archiver writes ON CONFLICT DO NOTHING so a redelivered event is a no-op.
	// org A holds two rows at this point — the seeded objectstore ref and the
	// session_event ref written above — so a third would mean the duplicate
	// insert was not absorbed by the unique constraint.
	insertArtifactRef(t, f.ctx, f.db, artifactRefSeed{
		orgID: orgA, memoryID: memoryA, store: "objectstore", locator: "s3://bucket/a.json",
	})
	requireVisibleRefs(t, f.ctx, f.db, artifactScope{orgID: orgA, want: 2})
}

// artifactRefSeed is one memory_artifact_refs row the tests seed as the owner.
type artifactRefSeed struct {
	orgID    string
	memoryID string
	store    string
	locator  string
}

// artifactScope is the tenant a read or write is executed as, plus the row count
// it must see and — for the write cases — the memory the row names.
type artifactScope struct {
	orgID      string
	otherOrgID string
	memoryID   string
	want       int
}

// indexShape is one index name and the definition fragment it must contain.
type indexShape struct {
	name string
	want string
}

// deleteRefusal is one table and the tenant whose DELETE must be refused.
type deleteRefusal struct {
	table string
	orgID string
}

// privilegeCheck is one grant assertion: a role, a table, a verb and the answer
// has_table_privilege must give.
type privilegeCheck struct {
	role, table, privilege string
	want                   bool
}

func requireProvenanceTables(t *testing.T, ctx context.Context, db *sql.DB, want bool) {
	t.Helper()
	for _, table := range provenanceTables {
		var present bool
		err := db.QueryRowContext(ctx,
			`SELECT to_regclass('ibex_core.' || $1) IS NOT NULL`, table).Scan(&present)
		if err != nil {
			t.Fatalf("check table %s: %v", table, err)
		}
		if present != want {
			t.Fatalf("ibex_core.%s present = %v, want %v", table, present, want)
		}
	}
}

func insertArtifactRef(t *testing.T, ctx context.Context, db *sql.DB, seed artifactRefSeed) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli - literal statement with $N bind parameters; nothing is concatenated into the SQL.
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memory_artifact_refs (org_id, memory_id, store, locator)
			VALUES ($1::uuid, $2::uuid, $3, $4)
			ON CONFLICT DO NOTHING`,
			seed.orgID, seed.memoryID, seed.store, seed.locator)
		return err
	})
	if err != nil {
		t.Fatalf("insert artifact ref: %v", err)
	}
}

func requireIndexShape(t *testing.T, ctx context.Context, db *sql.DB, shape indexShape) {
	t.Helper()
	definition, err := indexDefinition(ctx, db, shape.name)
	if err != nil {
		t.Fatalf("read index %s: %v", shape.name, err)
	}
	if definition == "" {
		t.Fatalf("index %s is missing", shape.name)
	}
	if !strings.Contains(definition, shape.want) {
		t.Fatalf("index %s has the wrong shape\nwant definition containing: %s\ngot: %s",
			shape.name, shape.want, definition)
	}
}

// requireOrgPolicy pins that the table is guarded by the 000063 helper rather
// than an inline GUC comparison, so a later migration cannot reintroduce a
// forgeable predicate without failing here.
func requireOrgPolicy(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	var qual string
	err := db.QueryRowContext(ctx, `
		SELECT qual FROM pg_policies
		WHERE schemaname = 'ibex_core' AND tablename = $1`, table).Scan(&qual)
	if err != nil {
		t.Fatalf("read policy on %s: %v", table, err)
	}
	if !strings.Contains(qual, "rls_org_visible(org_id)") {
		t.Fatalf("policy on ibex_core.%s uses %q, want rls_org_visible(org_id)", table, qual)
	}
}

// requireNoForeignKey pins the purge-survival contract: a cascade from
// organizations or memories would delete the worklist with the rows it points at.
func requireNoForeignKey(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	var count int
	err := db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM pg_constraint
		WHERE conrelid = ('ibex_core.' || $1)::regclass AND contype = 'f'`, table).Scan(&count)
	if err != nil {
		t.Fatalf("count foreign keys on %s: %v", table, err)
	}
	if count != 0 {
		t.Fatalf("ibex_core.%s has %d foreign key(s); it must outlive an org purge", table, count)
	}
}

// requireTenantGrants pins the write verbs each identity holds. SELECT and
// INSERT are the archiver's and the saga's working set. DELETE is not: a ref is
// the only address of an external copy and a receipt is the proof a store was
// cleared, so a tenant identity able to delete either can turn every store into
// `not_applicable` or erase the evidence of an erasure in one statement.
// `ibex_service` keeps DELETE for operator-driven cleanup.
func requireTenantGrants(t *testing.T, ctx context.Context, db *sql.DB, table string) {
	t.Helper()
	for _, role := range []string{"ibex_app", "ibex_service"} {
		for _, privilege := range []string{"SELECT", "INSERT"} {
			requireTablePrivilege(t, ctx, db, privilegeCheck{
				role: role, table: table, privilege: privilege, want: true,
			})
		}
	}
	requireTablePrivilege(t, ctx, db, privilegeCheck{
		role: "ibex_service", table: table, privilege: "DELETE", want: true,
	})
	requireTablePrivilege(t, ctx, db, privilegeCheck{
		role: "ibex_app", table: table, privilege: "DELETE", want: false,
	})
}

func requireTablePrivilege(t *testing.T, ctx context.Context, db *sql.DB, check privilegeCheck) {
	t.Helper()
	var granted bool
	err := db.QueryRowContext(ctx,
		`SELECT has_table_privilege($1, ('ibex_core.' || $2)::regclass, $3)`,
		check.role, check.table, check.privilege).Scan(&granted)
	if err != nil {
		t.Fatalf("check %s on %s: %v", check.privilege, check.table, err)
	}
	if granted != check.want {
		t.Fatalf("%s %s on ibex_core.%s = %v, want %v",
			check.role, check.privilege, check.table, granted, check.want)
	}
}

// proofDeleteStatements are the literal DELETE statements the negative test
// attempts. Literals per table keep the identifier out of a formatted string
// (Bandit B608 shape) and out of a value a caller could influence.
var proofDeleteStatements = map[string]string{
	"memory_artifact_refs":   "DELETE FROM ibex_core.memory_artifact_refs WHERE org_id = $1::uuid",
	"erasure_store_receipts": "DELETE FROM ibex_core.erasure_store_receipts WHERE org_id = $1::uuid",
}

// requireAppDeleteRefused proves the grant is absent in practice, not only in
// `has_table_privilege`: the statement itself must fail with 42501.
func requireAppDeleteRefused(t *testing.T, ctx context.Context, db *sql.DB, refusal deleteRefusal) {
	t.Helper()
	statement, ok := proofDeleteStatements[refusal.table]
	if !ok {
		t.Fatalf("no DELETE statement for table %q", refusal.table)
	}
	err := withOrgContext(ctx, db, refusal.orgID, func(tx *sql.Tx) error {
		_, execErr := tx.ExecContext(ctx, statement, refusal.orgID)
		return execErr
	})
	requireSQLState(t, err, "42501", "ibex_app DELETE on ibex_core."+refusal.table)
}

func requireVisibleRefs(t *testing.T, ctx context.Context, db *sql.DB, scope artifactScope) {
	t.Helper()
	var count int
	err := withOrgContext(ctx, db, scope.orgID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx,
			`SELECT COUNT(*) FROM ibex_core.memory_artifact_refs`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count refs as org %q: %v", scope.orgID, err)
	}
	if count != scope.want {
		t.Fatalf("refs visible to org %q = %d, want %d", scope.orgID, count, scope.want)
	}
}

// requireAppInsertRefusedForOtherOrg proves WITH CHECK: a tenant pinned to org A
// cannot write a ref for org B, so the archiver cannot be talked into recording
// another tenant's provenance.
// appInsert is one "write a ref row as ibex_app" probe: the org the row names,
// and the SQLSTATE the write must produce (empty means it must succeed).
type appInsert struct {
	scope   artifactScope
	org     string
	wantErr string
}

func requireAppInsert(t *testing.T, ctx context.Context, db *sql.DB, probe appInsert) {
	t.Helper()
	err := withOrgContext(ctx, db, probe.scope.orgID, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.memory_artifact_refs (org_id, memory_id, store, locator)
			VALUES ($1::uuid, $2::uuid, 'session_event', '42')`,
			probe.org, probe.scope.memoryID)
		return err
	})
	if probe.wantErr == "" {
		if err != nil {
			t.Fatalf("own-org insert as ibex_app: %v", err)
		}
		return
	}
	requireSQLState(t, err, probe.wantErr, "cross-tenant insert")
}
