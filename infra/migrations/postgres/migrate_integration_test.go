//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

// testDSN is the DSN every test must use: the database the operator configured,
// which TestMain repairs once before the suite runs. The harness no longer
// rewrites it (see migrate_integration_main_test.go for why a per-run database
// was abandoned).
func testDSN() string {
	return baseTestDSN()
}

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	dsn := testDSN()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Skipf("postgres not available at %s: %v", RedactedDSN(dsn), err)
	}
	return db
}

func resetSchema(t *testing.T, db *sql.DB) {
	t.Helper()
	if err := resetSchemaConn(context.Background(), db); err != nil {
		t.Fatalf("%v", err)
	}
}

// resetSchemaConn empties the migrated schemas and clears the migration
// bookkeeping so the next Up starts from nothing.
//
// The schema drop is what makes the capability roles droppable: PostgreSQL roles
// are cluster-global, and `DROP ROLE` fails with SQLSTATE 2BP01 while the role
// still owns or is granted an object anywhere in the cluster. Dropping
// `ibex_core` and `ibex_billing` CASCADE removes every object and every grant
// those roles hold in this database, so the drops below normally succeed and the
// down migrations' own `DROP ROLE` statements work.
//
// The role drops stay best effort. A role that another database in the same
// cluster still uses cannot be dropped here (2BP01 names that database), which is
// not a harness failure: the migration files normalise a pre-existing role
// through their own idempotent guards (000004, 000036, 000064, 000068), which is
// what a provisioned second database relies on too.
func resetSchemaConn(ctx context.Context, db *sql.DB) error {
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_billing CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	// Capability roles first: they hold grantable privileges and memberships
	// that the schema drop does not remove. ibex_auth is dropped before
	// ibex_app because its ibex_app membership depends on that role. The
	// statements are literals so no role name is concatenated into SQL.
	for _, drop := range []struct{ name, statement string }{
		{"ibex_purge", "DROP ROLE IF EXISTS ibex_purge"},
		{"ibex_runtime", "DROP ROLE IF EXISTS ibex_runtime"},
		{"ibex_worker", "DROP ROLE IF EXISTS ibex_worker"},
		{"ibex_bootstrap", "DROP ROLE IF EXISTS ibex_bootstrap"},
		{"ibex_auth", "DROP ROLE IF EXISTS ibex_auth"},
		{"ibex_app", "DROP ROLE IF EXISTS ibex_app"},
	} {
		if _, err := db.ExecContext(ctx, drop.statement); err != nil {
			if isRoleInUse(err) {
				continue
			}
			return fmt.Errorf("drop role %s: %w", drop.name, err)
		}
	}
	return nil
}

// isRoleInUse reports SQLSTATE 2BP01 (dependent_objects_still_exist), the error
// PostgreSQL returns when a role still owns or is granted objects in another
// database of the cluster.
func isRoleInUse(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "2BP01"
}

func TestMigrateUpIdempotent(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("first up: %v", err)
	}
	if err := Up(dsn); err != nil {
		t.Fatalf("second up (expected no-op): %v", err)
	}

	v, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatal("expected clean migration state")
	}
	want := maxEmbeddedMigrationVersion(t)
	if v != want {
		t.Fatalf("expected version %d, got %d", want, v)
	}
}

// evidencePlaneVersion is 000036, the migration that creates the two evidence
// capability roles. Rolling back below it runs the down file's
// `DROP ROLE ibex_evidence_relay` and `DROP ROLE ibex_service`.
const evidencePlaneVersion = 36

// TestEvidencePlane_MigrationDownDropsClusterGlobalRoles proves the one thing the
// per-run database could not give the suite: 000036's role drops succeeding.
//
// Both roles are cluster-global, and they hold privileges on objects in this
// database. The drop therefore succeeds only because the schema reset removed the
// schemas that carried those privileges — the same reset TestMain runs before the
// suite. Under the per-run-database harness this rollback failed with SQLSTATE
// 2BP01 naming the migrated database the roles still held grants in, which is why
// that harness was removed (see migrate_integration_main_test.go).
func TestEvidencePlane_MigrationDownDropsClusterGlobalRoles(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	requireRolesExist(t, db, "ibex_service", "ibex_evidence_relay")

	downToVersion(t, dsn, evidencePlaneVersion-1)

	requireRolesDropped(t, db, "ibex_service", "ibex_evidence_relay")

	// The up files recreate both roles, so a rollback that left an object behind
	// would surface here rather than in a later test.
	if err := Up(dsn); err != nil {
		t.Fatalf("re-up after rollback: %v", err)
	}
	requireRolesExist(t, db, "ibex_service", "ibex_evidence_relay")
}

// requireRolesExist fails unless every named role exists in the cluster.
func requireRolesExist(t *testing.T, db *sql.DB, names ...string) {
	t.Helper()
	for _, name := range names {
		if !roleExists(t, db, name) {
			t.Fatalf("role %s is missing; the migration set must create it", name)
		}
	}
}

// requireRolesDropped fails if any named role still exists in the cluster.
func requireRolesDropped(t *testing.T, db *sql.DB, names ...string) {
	t.Helper()
	for _, name := range names {
		if roleExists(t, db, name) {
			t.Fatalf("role %s survived the rollback; its down migration did not drop it", name)
		}
	}
}

// roleExists reports whether name is a cluster role. Roles are cluster-global, so
// the answer does not depend on the database the connection is attached to.
func roleExists(t *testing.T, db *sql.DB, name string) bool {
	t.Helper()
	var exists bool
	if err := db.QueryRowContext(context.Background(),
		`SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)`, name).Scan(&exists); err != nil {
		t.Fatalf("check role %s: %v", name, err)
	}
	return exists
}

func TestSchemaObjectsExist(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	tables := []string{
		"organizations", "tokens", "users", "agents",
		"directives", "directive_versions", "sessions", "checkpoints",
		"memories", "memory_labels", "memory_relationships",
		"memory_conflict_escalations",
	}
	assertCoreTablesExist(t, ctx, db, tables)
	assertCoreTablesRLSEnabled(t, ctx, db, tables)
}

func TestIbexAppRoleAttributes_NoSuperuserNoBypassRLS(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()
	var rolsuper, rolbypassrls bool
	err := db.QueryRowContext(ctx, `
		SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'ibex_app'
	`).Scan(&rolsuper, &rolbypassrls)
	if err != nil {
		t.Fatalf("pg_roles: %v", err)
	}
	if rolsuper || rolbypassrls {
		t.Fatalf("ibex_app rolsuper=%v rolbypassrls=%v", rolsuper, rolbypassrls)
	}
}

func TestOperatorActionLedgerExists(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	ctx := context.Background()
	assertCoreTablesExist(t, ctx, db, []string{"operator_action_ledger", "user_totp_secrets", "org_model_policy_meta"})
	assertCoreTablesRLSEnabled(t, ctx, db, []string{"operator_action_ledger", "user_totp_secrets", "org_model_policy_meta"})
}

func TestRLSUsersAndAgentsIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	orgA, orgB := seedTwoOrgsWithAgents(t, ctx, db)
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "agents", orgID: "", want: 0})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "agents", orgID: orgA, want: 1})
	assertTableCount(t, ctx, tableCountCheck{db: db, table: "agents", orgID: orgB, want: 1})
}

func TestTokenForeignKeysEnforced(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()

	var orgA string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org A', 'org-a-tok-fk') RETURNING id::text`).Scan(&orgA)
	})
	if err != nil {
		t.Fatalf("seed org: %v", err)
	}

	nonexistentUser := uuid.New().String()
	// Fixed values: this test only needs a valid token row whose user FK fails.
	hash := "hash_fk_violation_fixed"
	prefix := "ibex_pat_fkprefix_fixed"
	// Attempt to insert a token with a non-existent user_id must fail with FK violation.
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens
				(org_id, type, hash, prefix, name, permissions, is_revoked, expires_at, user_id)
			VALUES
				($1::uuid, 'pat', $2, $3, $4, $5, false, NULL, $6::uuid)`,
			orgA,
			hash,
			prefix,
			"token-fk-violation",
			0,
			nonexistentUser,
		)
		return err
	})
	if err == nil {
		t.Fatal("expected FK violation error, got nil")
	}
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		if pqErr.Code != "23503" {
			t.Fatalf("expected SQLSTATE 23503, got %s", pqErr.Code)
		}
		return
	}
	t.Fatalf("expected *pq.Error, got %T: %v", err, err)
}

func TestRLSCrossTenant(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()

	var orgA, orgB string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org A', 'org-a') RETURNING id::text`).Scan(&orgA)
	})
	if err != nil {
		t.Fatalf("insert org A: %v", err)
	}
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org B', 'org-b') RETURNING id::text`).Scan(&orgB)
	})
	if err != nil {
		t.Fatalf("insert org B: %v", err)
	}

	// No org context: fail closed (zero rows).
	var count int
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.organizations`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count without context: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected 0 organizations without context, got %d", count)
	}

	// Org A context: only org A visible.
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgA)
		if err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.organizations`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count with org A context: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 organization for org A context, got %d", count)
	}

	var seenSlug string
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgA)
		if err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `SELECT slug FROM ibex_core.organizations`).Scan(&seenSlug)
	})
	if err != nil {
		t.Fatalf("select with org A: %v", err)
	}
	if seenSlug != "org-a" {
		t.Fatalf("expected org-a, got %q", seenSlug)
	}
}

func TestRLSTokensIsolation(t *testing.T) {
	dsn := testDSN()
	db := openTestDB(t)
	defer db.Close()
	resetSchema(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	var orgA, orgB string

	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org A', 'org-a-tok') RETURNING id::text`).Scan(&orgA); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org B', 'org-b-tok') RETURNING id::text`).Scan(&orgB)
	})
	if err != nil {
		t.Fatalf("insert orgs: %v", err)
	}

	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions)
			VALUES ($1::uuid, 'pat', 'hash-b', 'ibex_', 'token-b', 0)`, orgB)
		return err
	})
	if err != nil {
		t.Fatalf("insert token org B: %v", err)
	}

	var count int
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgA)
		if err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.tokens`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count tokens: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected 0 tokens visible for org A, got %d", count)
	}
}

func withServiceAccount(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		return fmt.Errorf("set service account: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func withAppRole(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		return fmt.Errorf("set role ibex_app: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}
