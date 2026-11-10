package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// ErrInvalidTenantID is returned when a tenant-scoped operation is attempted
// without a well-formed organisation id. It fails closed in Go rather than
// issuing a query whose zero-row result would be indistinguishable from a real
// miss.
var ErrInvalidTenantID = errors.New("repository: invalid tenant id")

// withTenant runs fn inside one transaction that assumes the RLS-enforcing
// ibex_app role and pins app.current_org_id for that transaction only.
//
// The owner login (ibex) and the future ibex_runtime login are both members of
// ibex_app, so SET LOCAL ROLE works without a DSN change. SET LOCAL is used
// because the *sql.DB is pooled: a session-level SET would leak the role and
// the tenant selector into the next borrower of the connection.
func withTenant(ctx context.Context, db *sql.DB, orgID string, fn func(*sql.Tx) error) error {
	if err := requireTenantID(orgID); err != nil {
		return err
	}
	return withTx(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
			return fmt.Errorf("pin ibex_app: %w", err)
		}
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID); err != nil {
			return fmt.Errorf("set org context: %w", err)
		}
		return fn(tx)
	})
}

// withReaderTx runs fn inside one transaction with no role pin and no tenant
// GUC. It is used only for SECURITY DEFINER readers whose reach comes from the
// function owner, not from a session flag, so the same call works under the
// owner login and under a future ibex_runtime DSN.
func withReaderTx(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	return withTx(ctx, db, fn)
}

// withTx owns the begin/rollback/commit lifecycle so callers only express the
// statement they need.
func withTx(ctx context.Context, db *sql.DB, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

// requireTenantID rejects an empty, zero, or malformed organisation id before
// any SQL runs, so a programming error fails closed instead of looking like a
// tenant miss. uuid.Parse also removes the risk of a 22P02 cast error.
func requireTenantID(orgID string) error {
	if orgID == "" {
		return fmt.Errorf("%w: empty", ErrInvalidTenantID)
	}
	parsed, err := uuid.Parse(orgID)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidTenantID, err)
	}
	if parsed == uuid.Nil {
		return fmt.Errorf("%w: zero uuid", ErrInvalidTenantID)
	}
	return nil
}
