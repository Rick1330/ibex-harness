//go:build integration

package testutil

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"testing"
	"time"

	"github.com/lib/pq"
)

// OpenDB opens a Postgres connection and skips the test when the database is unreachable.
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
// capability logins first (ProvisionCapabilityLogins) so the SCRAM verifier and
// connection limit are set.
func OpenRuntimeDB(t testing.TB, dsn string) *sql.DB {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse test DSN: %v", err)
	}
	parsed.User = url.UserPassword("ibex_runtime", RuntimeLoginTestPassword)
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
// the role wiring is wrong, not that tenant isolation is working.
func RequireNoPermissionDenied(t testing.TB, err error) {
	t.Helper()
	var pqErr *pq.Error
	if errors.As(err, &pqErr) && pqErr.Code == "42501" {
		t.Fatalf("postgres 42501 permission denied: role wiring is wrong, not isolation: %v", err)
	}
}

// WithServiceAccount runs fn in a transaction with app.is_service_account=true.
func WithServiceAccount(ctx context.Context, db *sql.DB, fn func(tx *sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
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

// WithAppRole runs fn in a transaction using the ibex_app role (RLS enforced).
func WithAppRole(ctx context.Context, db *sql.DB, fn func(tx *sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		return fmt.Errorf("set role: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

// MustSetOrgContext sets app.current_org_id on the transaction (RLS tenant scope).
func MustSetOrgContext(t testing.TB, tx *sql.Tx, orgID string) {
	t.Helper()
	ctx := context.Background()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID); err != nil {
		t.Fatalf("set org context: %v", err)
	}
}
