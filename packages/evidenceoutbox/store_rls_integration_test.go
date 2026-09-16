//go:build integration

package evidenceoutbox_test

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/lib/pq"
)

// withAppRole mirrors infra/migrations/postgres/migrate_integration_test.go —
// FORCE RLS is enforced for ibex_app, not for the superuser test DSN.
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

func TestIntegration_EvidenceRLS_CrossTenantIsolation(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	store := mustStore(t, db)

	orgA := seedOrg(t, db)
	orgB := seedOrg(t, db)
	traceA := strings.ReplaceAll(uuid.NewString(), "-", "")
	traceB := strings.ReplaceAll(uuid.NewString(), "-", "")
	persistMinimalRun(t, store, orgA, traceA)
	persistMinimalRun(t, store, orgB, traceB)

	ctx := context.Background()
	assertAppRoleTableCount(t, ctx, appRoleCount{db: db, table: "evidence_runs", orgID: orgA, want: 1})
	assertAppRoleTableCount(t, ctx, appRoleCount{db: db, table: "evidence_runs", orgID: orgB, want: 1})
	assertAppRoleTableCount(t, ctx, appRoleCount{db: db, table: "evidence_outbox", orgID: orgA, want: -1})
	assertAppRoleSeesOnlyOwnOrg(t, ctx, appRoleOrgs{db: db, orgA: orgA, orgB: orgB})

	runAID := loadRunID(t, ctx, db, orgA)
	assertCrossTenantUpdateBlocked(t, ctx, crossTenantUpdate{db: db, orgB: orgB, runAID: runAID})
}

type appRoleCount struct {
	db    *sql.DB
	table string
	orgID uuid.UUID
	want  int
}

func assertAppRoleTableCount(t *testing.T, ctx context.Context, a appRoleCount) {
	t.Helper()
	q, ok := evidenceTableCountSQL[a.table]
	if !ok {
		t.Fatalf("unknown evidence table %q", a.table)
	}
	var count int
	err := withAppRole(ctx, a.db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, a.orgID.String()); err != nil {
			return err
		}
		return tx.QueryRowContext(ctx, q).Scan(&count)
	})
	if err != nil {
		t.Fatalf("count %s org=%s: %v", a.table, a.orgID, err)
	}
	if a.want < 0 {
		if count < 1 {
			t.Fatalf("%s org=%s count=%d want >= 1", a.table, a.orgID, count)
		}
		return
	}
	if count != a.want {
		t.Fatalf("%s org=%s count=%d want %d", a.table, a.orgID, count, a.want)
	}
}

// evidenceTableCountSQL whitelists table names (no fmt.Sprintf into SQL).
var evidenceTableCountSQL = map[string]string{
	"session_events":               `SELECT COUNT(*) FROM ibex_core.session_events`,
	"evidence_runs":                `SELECT COUNT(*) FROM ibex_core.evidence_runs`,
	"evidence_spans":               `SELECT COUNT(*) FROM ibex_core.evidence_spans`,
	"evidence_events":              `SELECT COUNT(*) FROM ibex_core.evidence_events`,
	"evidence_assembly_metrics":    `SELECT COUNT(*) FROM ibex_core.evidence_assembly_metrics`,
	"evidence_score_candidates":    `SELECT COUNT(*) FROM ibex_core.evidence_score_candidates`,
	"evidence_directive_snapshots": `SELECT COUNT(*) FROM ibex_core.evidence_directive_snapshots`,
	"evidence_tool_audits":         `SELECT COUNT(*) FROM ibex_core.evidence_tool_audits`,
	"evidence_outbox":              `SELECT COUNT(*) FROM ibex_core.evidence_outbox`,
}

var evidenceTableOrgCountSQL = map[string]string{
	"session_events":               `SELECT COUNT(*) FROM ibex_core.session_events WHERE org_id = $1`,
	"evidence_runs":                `SELECT COUNT(*) FROM ibex_core.evidence_runs WHERE org_id = $1`,
	"evidence_spans":               `SELECT COUNT(*) FROM ibex_core.evidence_spans WHERE org_id = $1`,
	"evidence_events":              `SELECT COUNT(*) FROM ibex_core.evidence_events WHERE org_id = $1`,
	"evidence_assembly_metrics":    `SELECT COUNT(*) FROM ibex_core.evidence_assembly_metrics WHERE org_id = $1`,
	"evidence_score_candidates":    `SELECT COUNT(*) FROM ibex_core.evidence_score_candidates WHERE org_id = $1`,
	"evidence_directive_snapshots": `SELECT COUNT(*) FROM ibex_core.evidence_directive_snapshots WHERE org_id = $1`,
	"evidence_tool_audits":         `SELECT COUNT(*) FROM ibex_core.evidence_tool_audits WHERE org_id = $1`,
	"evidence_outbox":              `SELECT COUNT(*) FROM ibex_core.evidence_outbox WHERE org_id = $1`,
}

type appRoleOrgs struct {
	db         *sql.DB
	orgA, orgB uuid.UUID
}

func assertAppRoleSeesOnlyOwnOrg(t *testing.T, ctx context.Context, a appRoleOrgs) {
	t.Helper()
	err := withAppRole(ctx, a.db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, a.orgB.String()); err != nil {
			return err
		}
		for table, q := range evidenceTableOrgCountSQL {
			var n int
			if err := tx.QueryRowContext(ctx, q, a.orgA).Scan(&n); err != nil {
				return fmt.Errorf("%s: %w", table, err)
			}
			if n != 0 {
				return fmt.Errorf("%s: orgB session saw %d orgA rows", table, n)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("cross-tenant select: %v", err)
	}
}

func loadRunID(t *testing.T, ctx context.Context, db *sql.DB, orgID uuid.UUID) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	// Superuser read for fixture id (FORCE RLS does not apply to superuser).
	if err := db.QueryRowContext(ctx,
		`SELECT id FROM ibex_core.evidence_runs WHERE org_id = $1 LIMIT 1`, orgID,
	).Scan(&id); err != nil {
		t.Fatalf("load run: %v", err)
	}
	return id
}

type crossTenantUpdate struct {
	db     *sql.DB
	orgB   uuid.UUID
	runAID uuid.UUID
}

func assertCrossTenantUpdateBlocked(t *testing.T, ctx context.Context, a crossTenantUpdate) {
	t.Helper()
	var updated int64
	err := withAppRole(ctx, a.db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, a.orgB.String()); err != nil {
			return err
		}
		res, err := tx.ExecContext(ctx, `
UPDATE ibex_core.evidence_runs SET status = 'error' WHERE id = $1`, a.runAID)
		if err != nil {
			return err
		}
		n, err := res.RowsAffected()
		if err != nil {
			return err
		}
		updated = n
		return nil
	})
	if err != nil {
		t.Fatalf("cross-tenant update: %v", err)
	}
	if updated != 0 {
		t.Fatalf("expected 0 rows updated across tenants, got %d", updated)
	}
}

func TestIntegration_OutboxRelayExecute_DeniedForIbexApp(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	store := mustStore(t, db)
	orgA := seedOrg(t, db)
	persistMinimalRun(t, store, orgA, strings.ReplaceAll(uuid.NewString(), "-", ""))

	ctx := context.Background()
	err := withAppRole(ctx, db, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgA.String()); err != nil {
			return err
		}
		rows, err := tx.QueryContext(ctx, `SELECT id FROM ibex_core.evidence_outbox_claim_pending(8)`)
		if err != nil {
			return err
		}
		defer func() { _ = rows.Close() }()
		return nil
	})
	if err == nil {
		t.Fatal("expected ibex_app EXECUTE on claim_pending to be denied")
	}
	if !isInsufficientPrivilege(err) {
		t.Fatalf("want permission denied, got: %v", err)
	}
}

func isInsufficientPrivilege(err error) bool {
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		return pqErr.Code == "42501"
	}
	// Fall back: lib/pq sometimes wraps the message only.
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "permission denied") || strings.Contains(msg, "42501")
}
