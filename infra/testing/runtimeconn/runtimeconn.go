//go:build integration

// Package runtimeconn holds the Postgres test helpers that integration tests
// need without importing the migration package. Nothing here pulls
// packages/proto/gen, so a CI job that does not generate protobuf can still
// compile these helpers.
package runtimeconn

import (
	"context"
	"database/sql"
	"errors"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/testcreds"
	"github.com/lib/pq"
)

const defaultTestDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

// DSN returns the integration Postgres DSN: POSTGRES_TEST_DSN when set, else
// the compose test default.
func DSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultTestDSN
}

// OpenDB opens a Postgres connection and skips the test when the database is
// unreachable.
func OpenDB(t testing.TB, dsn string) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		t.Skipf("postgres not available: %v", err)
	}
	return db
}

// OpenRuntimeDB connects with the ibex_runtime capability login. Provision the
// capability logins first (pgprovision.CapabilityLogins) so the SCRAM verifier
// and connection limit are set.
func OpenRuntimeDB(t testing.TB, dsn string) *sql.DB {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword("ibex_runtime", testcreds.RuntimeLoginTestPassword)
	db, err := sql.Open("postgres", parsed.String())
	if err != nil {
		t.Fatalf("open runtime pool: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		t.Fatalf("connect as ibex_runtime: %v", err)
	}
	return db
}

// RequireNoPermissionDenied fails when err is a Postgres 42501. That code means
// the role wiring for op is wrong, not that tenant isolation is working.
func RequireNoPermissionDenied(t testing.TB, err error, op string) {
	t.Helper()
	var pqErr *pq.Error
	if errors.As(err, &pqErr) && pqErr.Code == "42501" {
		t.Fatalf("%s: postgres 42501 permission denied: role wiring is wrong, not isolation: %v", op, err)
	}
}

// WithOwnerTx runs fn in a transaction on the owner pool. The tests that use it
// connect as the migration owner (a superuser), so no RLS GUC is needed to seed
// fixtures; keeping the GUC out also avoids writing the retired
// app.is_service_account flag.
func WithOwnerTx(ctx context.Context, db *sql.DB, fn func(tx *sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

// ResetCapabilityRoles drops the capability logins so a from-scratch migration
// recreates them. Roles and memberships are cluster-global: dropping only the
// schemas leaves a credentialed ibex_worker behind, and 000064 refuses to attach
// the modelled memberships to a role it did not create.
//
// Statements are literals so no role name is concatenated into SQL, and each
// error is ignored on purpose: DROP ROLE legitimately fails while another
// database in the cluster still holds privileges for the role.
func ResetCapabilityRoles(ctx context.Context, db *sql.DB) {
	for _, statement := range []string{
		`DROP ROLE IF EXISTS ibex_purge`,
		`DROP ROLE IF EXISTS ibex_runtime`,
		`DROP ROLE IF EXISTS ibex_worker`,
		`DROP ROLE IF EXISTS ibex_bootstrap`,
		`DROP ROLE IF EXISTS ibex_auth`,
	} {
		// nosemgrep: go_sql_rule-concat-sqli -- the statement is a compile-time literal from a fixed allowlist; no caller input reaches the SQL text.
		_, _ = db.ExecContext(ctx, statement)
	}
}
