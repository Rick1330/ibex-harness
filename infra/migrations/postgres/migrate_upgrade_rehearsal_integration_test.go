//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"slices"
	"testing"
	"time"
)

// releasedSchemaVersion is the migration version shipped at tag v0.1.9: 39
// up/down pairs, 78 files, pinned by migrate_released_set_test.go.
const releasedSchemaVersion = 39

// upgradeSeed is what the rehearsal creates at v0.1.9 and looks for again after
// the upgrade and after the rollback.
type upgradeSeed struct {
	orgA, orgB  string
	memoryA     string
	memoryB     string
	outboxEvent string
}

// upgradeToken is one seeded token row. The two tokens use distinct prefixes so
// 000070's duplicate precheck passes and 000071's CREATE UNIQUE INDEX
// CONCURRENTLY builds against pre-existing rows.
type upgradeToken struct {
	orgID, prefix, hash string
}

// upgradeMemory is one seeded memory row. deleted=true sets deleted_at, which is
// the state 000045's conditional UPDATE must turn into a tombstone.
type upgradeMemory struct {
	orgID, agentID, content, status string
	deleted                         bool
}

// memoryLifecycle is the tombstone flag and revision 000045 must produce.
type memoryLifecycle struct {
	tombstoned bool
	revision   int64
}

// memoryLifecycleCheck is a memory id and the lifecycle state expected for it.
type memoryLifecycleCheck struct {
	db   *sql.DB
	id   string
	want memoryLifecycle
}

// tokenResolution is a prefix and the organization it must resolve to.
type tokenResolution struct {
	prefix, orgID string
}

// countCheck is a table, the literal query that counts it, and the expected
// count.
type countCheck struct {
	name, query string
	want        int
}

// prefixIndexCheck is a token-prefix index and whether it must be unique.
type prefixIndexCheck struct {
	name   string
	unique bool
}

// TestUpgradeRehearsal_V019ToHead applies the released v0.1.9 schema, seeds it,
// upgrades to head, rolls back to v0.1.9, and upgrades again. Every .sql file at
// v0.1.9 is byte-identical on main, so migrations 1..39 applied from this
// checkout are the released schema; the pin test proves the files have not moved
// since.
//
// The database is opened here rather than through openTestDB on purpose: that
// helper skips an unreachable database, and a rehearsal that silently skips is
// the hole this test exists to close. db-migrate-smoke fails earlier when
// Postgres is down, so a failure here is the honest report.
func TestUpgradeRehearsal_V019ToHead(t *testing.T) {
	dsn := testDSN()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer func() { _ = db.Close() }()
	pingCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		t.Fatalf("postgres not reachable at %s: %v", RedactedDSN(dsn), err)
	}

	resetSchema(t, db)
	applyReleasedSchema(t, dsn)
	seed := seedUpgradeFixture(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up to head: %v", err)
	}
	assertVersionAt(t, dsn, maxEmbeddedMigrationVersion(t))
	assertUpgradeFacts(t, db, seed)

	// 000045's down refuses to drop lifecycle state while a tombstoned memory
	// exists (pinned by requireGuardedDownRefused in
	// migrate_memories_integration_test.go). The tombstone is exactly the proof
	// that this span is real, so the rollback cannot carry it: remove that one
	// row, roll back to the released version, and re-seed it there so the second
	// Up proves the conditional transformation again.
	deleteUpgradeMemory(t, db, seed.memoryB)
	rewindToVersion(t, dsn, releasedSchemaVersion)
	assertVersionAt(t, dsn, releasedSchemaVersion)
	assertRowCounts(t, db, 1)
	assertMemoryRowExists(t, db, seed.memoryA)

	seed.memoryB = seedDeletedMemory(t, db, seed)
	if err := Up(dsn); err != nil {
		t.Fatalf("re-up to head: %v", err)
	}
	assertVersionAt(t, dsn, maxEmbeddedMigrationVersion(t))
	assertUpgradeFacts(t, db, seed)
}

// applyReleasedSchema migrates the database to exactly the v0.1.9 schema through
// the package's own migration instance. Steps(39) from NilVersion applies 1..39;
// the version is asserted immediately so an off-by-one fails here instead of
// letting the rehearsal replay the wrong span.
func applyReleasedSchema(t *testing.T, dsn string) {
	t.Helper()
	m, err := newMigrate(dsn)
	if err != nil {
		t.Fatalf("migrate instance: %v", err)
	}
	err = m.Steps(int(releasedSchemaVersion))
	closeMigrate(m)
	if err != nil {
		t.Fatalf("steps to v%d: %v", releasedSchemaVersion, err)
	}
	assertVersionAt(t, dsn, releasedSchemaVersion)
}

// assertVersionAt requires the database to sit at want with no dirty flag.
func assertVersionAt(t *testing.T, dsn string, want uint) {
	t.Helper()
	got, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatalf("migration state is dirty at v%d", got)
	}
	if got != want {
		t.Fatalf("migration version = %d, want %d", got, want)
	}
}

// rewindToVersion rolls back one migration at a time until the database sits at
// floor, naming the version that failed.
func rewindToVersion(t *testing.T, dsn string, floor uint) {
	t.Helper()
	for {
		version, dirty, err := Version(dsn)
		if err != nil {
			t.Fatalf("version: %v", err)
		}
		if dirty {
			t.Fatalf("migration state is dirty at v%d", version)
		}
		if version == floor {
			return
		}
		if version < floor {
			t.Fatalf("cannot down to v%d from v%d", floor, version)
		}
		if err := Down(dsn); err != nil {
			t.Fatalf(downErrFormat, version, err)
		}
	}
}

// seedUpgradeFixture seeds the released schema with two tenants, two tokens with
// distinct prefixes, one pending outbox row and two memories whose lifecycle
// state 000045 must transform conditionally.
func seedUpgradeFixture(t *testing.T, db *sql.DB) upgradeSeed {
	t.Helper()
	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	seed := upgradeSeed{orgA: orgA, orgB: orgB}
	agentA := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgA, slug: "agent-a"})
	agentB := lookupAgentID(t, ctx, agentLookup{db: db, orgID: orgB, slug: "agent-b"})

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := insertUpgradeToken(ctx, tx, upgradeToken{orgID: orgA, prefix: "ibx_a_0001", hash: "hash-upgrade-a"}); err != nil {
			return err
		}
		if err := insertUpgradeToken(ctx, tx, upgradeToken{orgID: orgB, prefix: "ibx_b_0001", hash: "hash-upgrade-b"}); err != nil {
			return err
		}
		eventID, err := insertUpgradeOutbox(ctx, tx, orgA)
		if err != nil {
			return err
		}
		seed.outboxEvent = eventID
		if seed.memoryA, err = insertUpgradeMemory(ctx, tx, upgradeMemory{
			orgID: orgA, agentID: agentA, content: "upgrade-active", status: "active",
		}); err != nil {
			return err
		}
		seed.memoryB, err = insertUpgradeMemory(ctx, tx, upgradeMemory{
			orgID: orgB, agentID: agentB, content: "upgrade-deleted", status: "deleted", deleted: true,
		})
		return err
	})
	if err != nil {
		t.Fatalf("seed upgrade fixture: %v", err)
	}
	return seed
}

// insertUpgradeToken writes one token row with the columns v0.1.9 requires.
func insertUpgradeToken(ctx context.Context, tx *sql.Tx, seed upgradeToken) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions)
		VALUES ($1::uuid, 'pat', $2, $3, $4, 0)`,
		seed.orgID, seed.hash, seed.prefix, "token-"+seed.prefix)
	return err
}

// insertUpgradeOutbox writes one pending evidence-outbox row and returns its
// event id. 000040 adds payload_digest_scheme NOT NULL DEFAULT later, so this row
// is a real default backfill on a row that already exists.
func insertUpgradeOutbox(ctx context.Context, tx *sql.Tx, orgID string) (string, error) {
	var eventID string
	err := tx.QueryRowContext(ctx, `
		INSERT INTO ibex_core.evidence_outbox
			(org_id, event_id, aggregate_id, aggregate_seq, event_type, payload, payload_digest)
		VALUES ($1::uuid, gen_random_uuid(), 'upgrade-rehearsal', 1, 'rehearsal.seeded',
			'{}'::jsonb, 'digest-upgrade-rehearsal')
		RETURNING event_id::text`, orgID).Scan(&eventID)
	return eventID, err
}

// insertUpgradeMemory writes one memory row and returns its id. A deleted memory
// also gets deleted_at, the second arm of 000045's conditional UPDATE.
func insertUpgradeMemory(ctx context.Context, tx *sql.Tx, seed upgradeMemory) (string, error) {
	var deletedAt any
	if seed.deleted {
		deletedAt = time.Now().UTC()
	}
	var id string
	err := tx.QueryRowContext(ctx, `
		INSERT INTO ibex_core.memories
			(org_id, agent_id, content, content_hash, content_tokens, category, status, deleted_at)
		VALUES ($1::uuid, $2::uuid, $3, $4, 1, 'factual', $5, $6)
		RETURNING id::text`,
		seed.orgID, seed.agentID, seed.content, "hash-"+seed.content, seed.status, deletedAt).Scan(&id)
	return id, err
}

// assertUpgradeFacts checks every invariant the upgrade must preserve or produce.
func assertUpgradeFacts(t *testing.T, db *sql.DB, seed upgradeSeed) {
	t.Helper()
	assertRowCounts(t, db, 2)
	assertMemoryLifecycle(t, memoryLifecycleCheck{db: db, id: seed.memoryA, want: memoryLifecycle{tombstoned: false, revision: 1}})
	assertMemoryLifecycle(t, memoryLifecycleCheck{db: db, id: seed.memoryB, want: memoryLifecycle{tombstoned: true, revision: 1}})
	assertEvidenceDigestScheme(t, db, seed.outboxEvent)
	assertUnvalidatedConstraintSet(t, db)
	assertTokenPrefixIndexes(t, db)
	assertTokenResolvesToOrg(t, db, tokenResolution{prefix: "ibx_b_0001", orgID: seed.orgB})
}

// upgradeCountChecks are the seeded row counts, one literal query per table. The
// memory count is a parameter because the rollback leg deliberately removes the
// tombstoned row 000045's down guard refuses to roll past.
func upgradeCountChecks(memoryCount int) []countCheck {
	return []countCheck{
		{name: "organizations", query: `SELECT COUNT(*) FROM ibex_core.organizations`, want: 2},
		{name: "users", query: `SELECT COUNT(*) FROM ibex_core.users`, want: 2},
		{name: "agents", query: `SELECT COUNT(*) FROM ibex_core.agents`, want: 2},
		{name: "tokens", query: `SELECT COUNT(*) FROM ibex_core.tokens`, want: 2},
		{name: "memories", query: `SELECT COUNT(*) FROM ibex_core.memories`, want: memoryCount},
		{name: "evidence_outbox", query: `SELECT COUNT(*) FROM ibex_core.evidence_outbox`, want: 1},
	}
}

// assertRowCounts requires every seeded table to hold exactly its seeded count,
// so an upgrade or rollback that drops a row fails here.
func assertRowCounts(t *testing.T, db *sql.DB, memoryCount int) {
	t.Helper()
	for _, check := range upgradeCountChecks(memoryCount) {
		var got int
		err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
			return tx.QueryRowContext(context.Background(), check.query).Scan(&got)
		})
		if err != nil {
			t.Fatalf("count %s: %v", check.name, err)
		}
		if got != check.want {
			t.Fatalf("%s count = %d, want %d", check.name, got, check.want)
		}
	}
}

// deleteUpgradeMemory removes one seeded memory. It is a precondition of the
// rollback, not a convenience: 000045's down refuses while any tombstoned row
// exists, and the tombstone is exactly what this rehearsal seeds.
func deleteUpgradeMemory(t *testing.T, db *sql.DB, id string) {
	t.Helper()
	err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(context.Background(), `DELETE FROM ibex_core.memories WHERE id = $1::uuid`, id)
		return err
	})
	if err != nil {
		t.Fatalf("delete seeded memory: %v", err)
	}
}

// seedDeletedMemory re-seeds the deleted memory at the released version so the
// second Up runs 000045's conditional transformation again.
func seedDeletedMemory(t *testing.T, db *sql.DB, seed upgradeSeed) string {
	t.Helper()
	ctx := context.Background()
	agentB := lookupAgentID(t, ctx, agentLookup{db: db, orgID: seed.orgB, slug: "agent-b"})
	var id string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var err error
		id, err = insertUpgradeMemory(ctx, tx, upgradeMemory{
			orgID: seed.orgB, agentID: agentB, content: "upgrade-deleted", status: "deleted", deleted: true,
		})
		return err
	})
	if err != nil {
		t.Fatalf("re-seed deleted memory: %v", err)
	}
	return id
}

// assertMemoryRowExists requires the seeded memory to have survived the
// rollback.
func assertMemoryRowExists(t *testing.T, db *sql.DB, id string) {
	t.Helper()
	var exists bool
	err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(),
			`SELECT EXISTS (SELECT 1 FROM ibex_core.memories WHERE id = $1::uuid)`, id).Scan(&exists)
	})
	if err != nil {
		t.Fatalf("check memory %s: %v", id, err)
	}
	if !exists {
		t.Fatalf("memory %s did not survive the rollback", id)
	}
}

// assertMemoryLifecycle requires one memory's tombstone flag and lifecycle
// revision.
func assertMemoryLifecycle(t *testing.T, check memoryLifecycleCheck) {
	t.Helper()
	var got memoryLifecycle
	err := withServiceAccount(context.Background(), check.db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `
			SELECT tombstoned, lifecycle_revision
			FROM ibex_core.memories WHERE id = $1::uuid`, check.id).Scan(&got.tombstoned, &got.revision)
	})
	if err != nil {
		t.Fatalf("read memory lifecycle: %v", err)
	}
	if got != check.want {
		t.Fatalf("memory lifecycle = %+v, want %+v", got, check.want)
	}
}

// assertEvidenceDigestScheme requires the pre-existing outbox row to have been
// backfilled with 000040's default.
func assertEvidenceDigestScheme(t *testing.T, db *sql.DB, eventID string) {
	t.Helper()
	var got string
	err := withServiceAccount(context.Background(), db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(), `
			SELECT payload_digest_scheme
			FROM ibex_core.evidence_outbox WHERE event_id = $1::uuid`, eventID).Scan(&got)
	})
	if err != nil {
		t.Fatalf("read payload_digest_scheme: %v", err)
	}
	if want := "postgres-jsonb-text/v1"; got != want {
		t.Fatalf("payload_digest_scheme = %q, want %q", got, want)
	}
}

// unvalidatedConstraintSet is the NOT VALID constraint set the migration head
// deliberately leaves behind. 000026 adds three agent CHECK constraints NOT
// VALID and no later migration validates them, so "none" is not the truth at
// head. Pinning the exact set keeps the intent: a fourth NOT VALID constraint
// shipped without its VALIDATE fails here by name.
func unvalidatedConstraintSet() []string {
	return []string{
		"agents_default_model_max",
		"agents_default_provider_max",
		"agents_description_max",
	}
}

// assertUnvalidatedConstraintSet requires the unvalidated constraints in the two
// migrated schemas to be exactly the pinned set.
func assertUnvalidatedConstraintSet(t *testing.T, db *sql.DB) {
	t.Helper()
	rows, err := db.QueryContext(context.Background(), `
		SELECT c.conname
		FROM pg_constraint c
		JOIN pg_namespace n ON n.oid = c.connamespace
		WHERE NOT c.convalidated
		  AND n.nspname IN ('ibex_core', 'ibex_billing')
		ORDER BY c.conname`)
	if err != nil {
		t.Fatalf("read unvalidated constraints: %v", err)
	}
	defer func() { _ = rows.Close() }()

	var got []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatalf("scan constraint: %v", err)
		}
		got = append(got, name)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate constraints: %v", err)
	}
	if want := unvalidatedConstraintSet(); !slices.Equal(got, want) {
		t.Fatalf("unvalidated constraints = %v, want %v", got, want)
	}
}

// assertTokenPrefixIndexes requires both token-prefix indexes to be valid and
// ready, with the unique one actually unique.
func assertTokenPrefixIndexes(t *testing.T, db *sql.DB) {
	t.Helper()
	for _, want := range []prefixIndexCheck{
		{name: "idx_tokens_prefix", unique: false},
		{name: "idx_tokens_prefix_unique", unique: true},
	} {
		assertPrefixIndex(t, db, want)
	}
}

// assertPrefixIndex requires one index to be usable and to enforce the
// uniqueness its migration declared.
func assertPrefixIndex(t *testing.T, db *sql.DB, want prefixIndexCheck) {
	t.Helper()
	var valid, ready, unique bool
	err := db.QueryRowContext(context.Background(), `
		SELECT i.indisvalid, i.indisready, i.indisunique
		FROM pg_index i
		WHERE i.indexrelid = to_regclass($1)`, "ibex_core."+want.name).Scan(&valid, &ready, &unique)
	if err != nil {
		t.Fatalf("read %s flags: %v", want.name, err)
	}
	if !prefixIndexUsable(valid, ready) {
		t.Fatalf("%s is not usable: valid=%v ready=%v", want.name, valid, ready)
	}
	if !prefixIndexEnforcesUniqueness(unique, want.unique) {
		t.Fatalf("%s unique=%v, want unique=%v", want.name, unique, want.unique)
	}
}

// prefixIndexUsable reports whether Postgres will use the index: a CREATE INDEX
// CONCURRENTLY that failed leaves indisvalid false and one still being built
// leaves indisready false, and either way the token-prefix lookup silently falls
// back to a sequential scan.
func prefixIndexUsable(valid, ready bool) bool {
	return valid && ready
}

// prefixIndexEnforcesUniqueness reports whether the index enforces the
// uniqueness the migration declared. 000071's whole point is a unique
// token-prefix index, so a non-unique index of that name would let two tokens
// share a prefix.
func prefixIndexEnforcesUniqueness(unique, wantUnique bool) bool {
	return unique == wantUnique
}

// assertTokenResolvesToOrg requires the auth reader to resolve the seeded prefix
// to exactly one row of the expected organization.
func assertTokenResolvesToOrg(t *testing.T, db *sql.DB, want tokenResolution) {
	t.Helper()
	var rows int
	var orgID string
	err := db.QueryRowContext(context.Background(), `
		SELECT COUNT(*), COALESCE(MIN(org_id), '')
		FROM ibex_core.auth_find_token_by_prefix($1)`, want.prefix).Scan(&rows, &orgID)
	if err != nil {
		t.Fatalf("resolve %s: %v", want.prefix, err)
	}
	if rows != 1 {
		t.Fatalf("auth_find_token_by_prefix(%q) returned %d rows, want 1", want.prefix, rows)
	}
	if orgID != want.orgID {
		t.Fatalf("auth_find_token_by_prefix(%q) resolved org %s, want %s", want.prefix, orgID, want.orgID)
	}
}
