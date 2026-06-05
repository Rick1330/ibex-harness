//go:build integration

package postgres

import (
	"context"
	"errors"
	"database/sql"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/lib/pq"
	"github.com/google/uuid"
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
	for _, table := range []string{"organizations", "tokens", "users", "agents"} {
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

	for _, table := range []string{"organizations", "tokens", "users", "agents"} {
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

	var orgA, orgB string
	var userA, agentA string
	var userB, agentB string
	err := withServiceAccount(ctx, db, func(tx *sql.Tx) error {
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org A', 'org-a') RETURNING id::text`).Scan(&orgA); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.organizations (name, slug)
			VALUES ('Org B', 'org-b') RETURNING id::text`).Scan(&orgB); err != nil {
			return err
		}

		// Seed one user + agent per org.
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.users (org_id, email, name)
			VALUES ($1::uuid, 'user-a@example.com', 'User A')
			RETURNING id::text`, orgA).Scan(&userA); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			VALUES ($1::uuid, $2::uuid, 'Agent A', 'agent-a')
			RETURNING id::text`, orgA, userA).Scan(&agentA); err != nil {
			return err
		}

		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.users (org_id, email, name)
			VALUES ($1::uuid, 'user-b@example.com', 'User B')
			RETURNING id::text`, orgB).Scan(&userB); err != nil {
			return err
		}
		if err := tx.QueryRowContext(ctx, `
			INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
			VALUES ($1::uuid, $2::uuid, 'Agent B', 'agent-b')
			RETURNING id::text`, orgB, userB).Scan(&agentB); err != nil {
			return err
		}

		return nil
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}

	// No org context: fail closed.
	var count int
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.agents`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count without context: %v", err)
	}
	if count != 0 {
		t.Fatalf("expected 0 agents without context, got %d", count)
	}

	// Org A context: only Org A visible.
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgA); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.agents`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count with org A context: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 agent for org A context, got %d", count)
	}

	// Cross-org must not be visible.
	err = withAppRole(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgB); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, `SELECT COUNT(*) FROM ibex_core.agents`).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count with org B context: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected 1 agent for org B context, got %d", count)
	}

	_ = agentA
	_ = agentB
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
