//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"testing"

	"github.com/lib/pq"
)

// tenancyFixture centralises the migration harness and the seeded ids so tests
// and helpers take one small struct instead of long parameter lists.
type tenancyFixture struct {
	t       *testing.T
	dsn     string
	db      *sql.DB
	ctx     context.Context
	orgID   string
	userID  string
	agentID string
}

func newTenancyFixture(t *testing.T) *tenancyFixture {
	t.Helper()
	f := &tenancyFixture{t: t, dsn: testDSN(), ctx: context.Background(), db: openTestDB(t)}
	t.Cleanup(func() { _ = f.db.Close() })
	resetSchema(t, f.db)
	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	return f
}

// seedTenant creates one org, user and agent as the owner connection. RLS is
// bypassed for the owner, which is what the migration harness uses to seed.
func (f *tenancyFixture) seedTenant() {
	f.t.Helper()
	if err := f.db.QueryRowContext(f.ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ('Tenancy Org', 'tenancy-org') RETURNING id::text`).Scan(&f.orgID); err != nil {
		f.t.Fatalf("seed org: %v", err)
	}
	if err := f.db.QueryRowContext(f.ctx, `
		INSERT INTO ibex_core.users (org_id, email, name)
		VALUES ($1::uuid, 'tenancy@example.com', 'Tenancy User') RETURNING id::text`, f.orgID).Scan(&f.userID); err != nil {
		f.t.Fatalf("seed user: %v", err)
	}
	if err := f.db.QueryRowContext(f.ctx, `
		INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
		VALUES ($1::uuid, $2::uuid, 'Tenancy Agent', 'tenancy-agent') RETURNING id::text`,
		f.orgID, f.userID).Scan(&f.agentID); err != nil {
		f.t.Fatalf("seed agent: %v", err)
	}
}

func (f *tenancyFixture) seedToken(prefix, hash string) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(f.ctx, `
		INSERT INTO ibex_core.tokens (org_id, type, hash, prefix, name, permissions)
		VALUES ($1::uuid, 'pat', $2, $3, 'reader', 0) RETURNING id::text`,
		f.orgID, hash, prefix).Scan(&id); err != nil {
		f.t.Fatalf("seed token: %v", err)
	}
	return id
}

// withRole runs fn in a transaction as role, optionally setting the org GUC.
// An empty orgID skips the GUC (used for the service/reader paths).
func (f *tenancyFixture) withRole(role, orgID string, fn func(*sql.Tx) error) error {
	return f.runRoleTx(role, func(tx *sql.Tx) error {
		if orgID != "" {
			if err := f.setOrgGUC(tx, orgID); err != nil {
				return err
			}
		}
		return fn(tx)
	})
}

// withRoleGUC is withRole but always sets the GUC, including the empty string.
func (f *tenancyFixture) withRoleGUC(role, guc string, fn func(*sql.Tx) error) error {
	return f.runRoleTx(role, func(tx *sql.Tx) error {
		if err := f.setOrgGUC(tx, guc); err != nil {
			return err
		}
		return fn(tx)
	})
}

func (f *tenancyFixture) runRoleTx(role string, fn func(*sql.Tx) error) error {
	tx, err := f.db.BeginTx(f.ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if role != "" {
		if _, err := tx.ExecContext(f.ctx, `SET LOCAL ROLE `+role); err != nil {
			return fmt.Errorf("set role %s: %w", role, err)
		}
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func (f *tenancyFixture) setOrgGUC(tx *sql.Tx, value string) error {
	if _, err := tx.ExecContext(f.ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, value); err != nil {
		return fmt.Errorf("set org guc: %w", err)
	}
	return nil
}

func (f *tenancyFixture) requireSQLSTATE(err error, code string) {
	f.t.Helper()
	if err == nil {
		f.t.Fatalf("expected SQLSTATE %s, got nil", code)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		f.t.Fatalf("expected *pq.Error, got %T: %v", err, err)
	}
	if string(pqErr.Code) != code {
		f.t.Fatalf("expected SQLSTATE %s, got %s: %v", code, pqErr.Code, err)
	}
}

func (f *tenancyFixture) roleBool(role, column string) bool {
	f.t.Helper()
	var value bool
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT `+column+` FROM pg_roles WHERE rolname = $1`, role).Scan(&value); err != nil {
		f.t.Fatalf("read %s.%s: %v", role, column, err)
	}
	return value
}

func (f *tenancyFixture) connLimit(role string) int {
	f.t.Helper()
	var value int
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT rolconnlimit FROM pg_roles WHERE rolname = $1`, role).Scan(&value); err != nil {
		f.t.Fatalf("read %s.rolconnlimit: %v", role, err)
	}
	return value
}

func (f *tenancyFixture) assertMembers(role string, want []string) {
	f.t.Helper()
	rows, err := f.db.QueryContext(f.ctx, `
		WITH RECURSIVE membership AS (
			SELECT am.roleid, am.member
			FROM pg_auth_members am
			WHERE am.roleid = (SELECT oid FROM pg_roles WHERE rolname = $1)
			UNION
			SELECT am.roleid, am.member
			FROM pg_auth_members am
			JOIN membership m ON am.roleid = m.member
		)
		SELECT r.rolname
		FROM membership m
		JOIN pg_roles r ON r.oid = m.member
		ORDER BY r.rolname`, role)
	if err != nil {
		f.t.Fatalf("members of %s: %v", role, err)
	}
	defer rows.Close()
	got := scanStrings(f.t, rows)
	if len(got) != len(want) {
		f.t.Fatalf("members of %s = %v, want %v", role, got, want)
	}
	for i := range got {
		if got[i] != want[i] {
			f.t.Fatalf("members of %s = %v, want %v", role, got, want)
		}
	}
}

func (f *tenancyFixture) assertNoMemberships(role string) {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT COUNT(*) FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = $1)`,
		role).Scan(&n); err != nil {
		f.t.Fatalf("memberships of %s: %v", role, err)
	}
	if n != 0 {
		f.t.Fatalf("%s must hold no membership, got %d", role, n)
	}
}

func scanStrings(t *testing.T, rows *sql.Rows) []string {
	t.Helper()
	var out []string
	for rows.Next() {
		var value string
		if err := rows.Scan(&value); err != nil {
			t.Fatalf("scan: %v", err)
		}
		out = append(out, value)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("rows: %v", err)
	}
	return out
}

func (f *tenancyFixture) roleCount(roles ...string) int {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT COUNT(*) FROM pg_roles WHERE rolname = ANY($1)`, pq.Array(roles)).Scan(&n); err != nil {
		f.t.Fatalf("pg_roles count: %v", err)
	}
	return n
}

func (f *tenancyFixture) assertConnLimit(role string, want int) {
	f.t.Helper()
	if got := f.connLimit(role); got != want {
		f.t.Fatalf("%s rolconnlimit = %d, want %d", role, got, want)
	}
}

func (f *tenancyFixture) indexExists(qualified string) bool {
	f.t.Helper()
	var exists bool
	if err := f.db.QueryRowContext(f.ctx,
		`SELECT to_regclass($1) IS NOT NULL`, qualified).Scan(&exists); err != nil {
		f.t.Fatalf("to_regclass %s: %v", qualified, err)
	}
	return exists
}

func assertVersion(t *testing.T, dsn string, want uint) {
	t.Helper()
	version, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatal("expected clean migration state")
	}
	if version != want {
		t.Fatalf("version = %d, want %d", version, want)
	}
}
