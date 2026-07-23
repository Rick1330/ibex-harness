//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func testDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return normalizePostgresDSN(dsn)
	}
	return defaultTestDSN
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
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP SCHEMA IF EXISTS ibex_core CASCADE`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
	_, err := db.ExecContext(ctx, `DROP ROLE IF EXISTS ibex_app`)
	if err != nil {
		t.Fatalf("drop role: %v", err)
	}
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
	if v != 8 {
		t.Fatalf("expected version 8, got %d", v)
	}
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
	for _, table := range []string{"organizations", "tokens", "users", "agents", "directives", "directive_versions"} {
		var exists bool
		err := db.QueryRowContext(ctx, `
			SELECT EXISTS (
				SELECT 1 FROM information_schema.tables
				WHERE table_schema = 'ibex_core' AND table_name = $1
			)`, table).Scan(&exists)
		if err != nil {
			t.Fatalf("check table %s: %v", table, err)
		}
		if !exists {
			t.Errorf("missing table ibex_core.%s", table)
		}
	}

	for _, table := range []string{"organizations", "tokens", "users", "agents", "directives", "directive_versions"} {
		var rls bool
		err := db.QueryRowContext(ctx, `
			SELECT c.relrowsecurity
			FROM pg_class c
			JOIN pg_namespace n ON n.oid = c.relnamespace
			WHERE n.nspname = 'ibex_core' AND c.relname = $1`, table).Scan(&rls)
		if err != nil {
			t.Fatalf("check rls %s: %v", table, err)
		}
		if !rls {
			t.Errorf("RLS not enabled on ibex_core.%s", table)
		}
	}
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
	assertAgentCount(t, agentCountCheck{ctx: ctx, db: db, orgID: "", want: 0})
	assertAgentCount(t, agentCountCheck{ctx: ctx, db: db, orgID: orgA, want: 1})
	assertAgentCount(t, agentCountCheck{ctx: ctx, db: db, orgID: orgB, want: 1})
}

func seedTwoOrgsWithAgents(t *testing.T, ctx context.Context, db *sql.DB) (orgA, orgB string) {
	t.Helper()
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		var err error
		orgA, err = insertOrg(ctx, tx, "Org A", "org-a")
		if err != nil {
			return err
		}
		orgB, err = insertOrg(ctx, tx, "Org B", "org-b")
		if err != nil {
			return err
		}
		if err := insertUserAndAgent(ctx, tx, orgA, userAgentSeed{
			email: "user-a@example.com", name: "User A", agent: "Agent A", slug: "agent-a",
		}); err != nil {
			return err
		}
		return insertUserAndAgent(ctx, tx, orgB, userAgentSeed{
			email: "user-b@example.com", name: "User B", agent: "Agent B", slug: "agent-b",
		})
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	return orgA, orgB
}

func insertOrg(ctx context.Context, tx *sql.Tx, name, slug string) (string, error) {
	var id string
	err := tx.QueryRowContext(ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ($1, $2) RETURNING id::text`, name, slug).Scan(&id)
	return id, err
}

type userAgentSeed struct {
	email, name, agent, slug string
}

func insertUserAndAgent(ctx context.Context, tx *sql.Tx, orgID string, seed userAgentSeed) error {
	var userID string
	if err := tx.QueryRowContext(ctx, `
		INSERT INTO ibex_core.users (org_id, email, name)
		VALUES ($1::uuid, $2, $3)
		RETURNING id::text`, orgID, seed.email, seed.name).Scan(&userID); err != nil {
		return err
	}
	_, err := tx.ExecContext(ctx, `
		INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
		VALUES ($1::uuid, $2::uuid, $3, $4)`, orgID, userID, seed.agent, seed.slug)
	return err
}

type agentCountCheck struct {
	ctx   context.Context
	db    *sql.DB
	orgID string
	want  int
}

func assertAgentCount(t *testing.T, check agentCountCheck) {
	t.Helper()
	var count int
	err := withAppRole(check.ctx, check.db, func(tx *sql.Tx) error {
		if check.orgID != "" {
			if _, err := tx.ExecContext(check.ctx, `SELECT set_config('app.current_org_id', $1, true)`, check.orgID); err != nil {
				return err
			}
		}
		return tx.QueryRowContext(check.ctx, `SELECT COUNT(*) FROM ibex_core.agents`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count agents (org=%q): %v", check.orgID, err)
	}
	if count != check.want {
		t.Fatalf("expected %d agents (org=%q), got %d", check.want, check.orgID, count)
	}
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
	// Attempt to insert a token with a non-existent user_id must fail with FK violation.
	err = withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_core.tokens
				(org_id, type, hash, prefix, name, permissions, is_revoked, expires_at, user_id)
			VALUES
				($1::uuid, 'pat', $2, $3, $4, $5, false, NULL, $6::uuid)`,
			orgA,
			"hash_fk_violation_"+uuid.New().String(),
			"ibex_pat_"+"fkprefix_"+uuid.New().String(),
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
