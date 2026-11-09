//go:build integration

package postgres

import (
	"database/sql"
	"testing"
)

// The idle-session sweep must reject a future cutoff, which would otherwise let
// a request-path caller abandon every tenant's live sessions.
func TestTenancySessionSweepBounds(t *testing.T) {
	f := newTenancyFixture(t)

	err := f.withRole("ibex_runtime", "", func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx,
			`SELECT * FROM ibex_core.sessions_abandon_idle(NOW() + interval '1 hour', 10)`)
		return err
	})
	f.requireSQLSTATE(err, "22023")

	err = f.withRole("ibex_runtime", "", func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx,
			`SELECT * FROM ibex_core.sessions_abandon_idle(NOW() - interval '30 minutes', 10)`)
		return err
	})
	if err != nil {
		t.Fatalf("past cutoff should succeed: %v", err)
	}
}

// The snapshot readers are unbounded by design; this proves the grants and that
// an empty table is a clean zero-row result.
func TestTenancySnapshotReaders(t *testing.T) {
	f := newTenancyFixture(t)

	if err := f.withRole("ibex_runtime", "", func(tx *sql.Tx) error {
		_, err := tx.ExecContext(f.ctx, `SELECT * FROM ibex_core.rate_limit_overrides_snapshot()`)
		return err
	}); err != nil {
		t.Fatalf("rate-limit snapshot: %v", err)
	}

	if err := f.withRole("ibex_worker", "", func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(f.ctx, `SELECT * FROM ibex_billing.active_periods()`); err != nil {
			return err
		}
		_, err := tx.ExecContext(f.ctx,
			`SELECT * FROM ibex_core.budget_reservations_expire_stale(interval '0', 10)`)
		return err
	}); err != nil {
		t.Fatalf("worker readers: %v", err)
	}
}

func TestTenancyBudgetSweepValidation(t *testing.T) {
	f := newTenancyFixture(t)
	for _, query := range []string{
		`SELECT * FROM ibex_core.budget_reservations_expire_stale(interval '-1 second', 10)`,
		`SELECT * FROM ibex_core.budget_reservations_expire_stale(interval '0', 0)`,
	} {
		err := f.withRole("ibex_worker", "", func(tx *sql.Tx) error {
			_, err := tx.ExecContext(f.ctx, query)
			return err
		})
		f.requireSQLSTATE(err, "22023")
	}
}
