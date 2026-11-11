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

// tenancyFixture is the shared migration harness. It owns the connection and
// the seeded ids; context is passed by the caller because storing it in a
// struct is unsafe and unnecessary.
type tenancyFixture struct {
	t       *testing.T
	dsn     string
	db      *sql.DB
	orgID   string
	userID  string
	agentID string
}

// tenantSeed holds one seeded tenant's ids.
type tenantSeed struct {
	orgID, userID, agentID string
}

// roleSpec is a role name plus an optional org GUC. A nil guc skips the GUC; a
// pointer to "" sets the empty value the regression tests need.
type roleSpec struct {
	name   string
	orgGUC *string
}

// membershipSpec is a role and the members it must have.
type membershipSpec struct {
	role string
	want []string
}

// tokenSeed is the prefix and hash for a seeded token.
type tokenSeed struct {
	prefix, hash string
}

// roleSet is a set of role names for a count query.
type roleSet struct {
	names []string
}

// connLimitCheck is a role and its expected connection limit.
type connLimitCheck struct {
	spec roleSpec
	want int
}

// indexName is a schema-qualified index name.
type indexName struct {
	qualified string
}

// versionCheck is an expected migration version.
type versionCheck struct {
	want uint
}

// sqlState is an expected SQLSTATE code.
type sqlState struct {
	code string
}

// roleFlags are the pg_roles booleans the role tests assert.
type roleFlags struct {
	super, bypass, login, inherit bool
}

// roleStatements maps an allowlisted role to its fixed SET LOCAL ROLE
// statement. The statement is a compile-time literal per role, so no SQL is
// formatted from a variable and a name outside the allowlist cannot reach the
// server.
var roleStatements = map[string]string{
	"ibex":                "SET LOCAL ROLE ibex",
	"ibex_app":            "SET LOCAL ROLE ibex_app",
	"ibex_service":        "SET LOCAL ROLE ibex_service",
	"ibex_purge":          "SET LOCAL ROLE ibex_purge",
	"ibex_runtime":        "SET LOCAL ROLE ibex_runtime",
	"ibex_worker":         "SET LOCAL ROLE ibex_worker",
	"ibex_bootstrap":      "SET LOCAL ROLE ibex_bootstrap",
	"ibex_auth":           "SET LOCAL ROLE ibex_auth",
	"ibex_evidence_relay": "SET LOCAL ROLE ibex_evidence_relay",
}

// roleStatement looks up an allowlisted role statement.
func roleStatement(name string) (string, error) {
	statement, ok := roleStatements[name]
	if !ok {
		return "", fmt.Errorf("unsupported role %q", name)
	}
	return statement, nil
}

// role returns a roleSpec without an org GUC.
func role(name string) roleSpec {
	return roleSpec{name: name}
}

// withGUC returns a copy of the roleSpec with the org GUC set.
func (r roleSpec) withGUC(value string) roleSpec {
	r.orgGUC = &value
	return r
}

// newTenancyFixture resets the schema, applies the migrations and returns the
// harness. The caller closes it through t.Cleanup.
func newTenancyFixture(t *testing.T) *tenancyFixture {
	t.Helper()
	f := &tenancyFixture{t: t, dsn: testDSN(), db: openTestDB(t)}
	t.Cleanup(func() { _ = f.db.Close() })
	resetSchema(t, f.db)
	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	return f
}

// sub returns a copy of the fixture bound to a subtest, so a helper that fails
// reports against the subtest instead of calling FailNow on the parent test.
// t.Cleanup and the connection are shared through the copy.
func (f *tenancyFixture) sub(t *testing.T) *tenancyFixture {
	clone := *f
	clone.t = t
	return &clone
}

// rewindTo applies one-migration Down steps until the schema sits at floor.
// Tests that need a pre-migration cluster state use it to reach the version
// whose up file they are about to exercise against a hand-built shape.
func rewindTo(t *testing.T, f *tenancyFixture, floor uint) {
	t.Helper()
	for {
		version, dirty, err := Version(f.dsn)
		if err != nil {
			t.Fatalf("version while rewinding to %d: %v", floor, err)
		}
		if dirty {
			t.Fatalf("cannot rewind to %d from a dirty migration state", floor)
		}
		if version <= floor {
			return
		}
		if err := Down(f.dsn); err != nil {
			t.Fatalf("down from %d: %v", version, err)
		}
	}
}

// seedTenant creates the primary org, user and agent and stores their ids.
func (f *tenancyFixture) seedTenant(ctx context.Context) {
	f.t.Helper()
	seed := f.seedTenantNamed(ctx, "tenancy-org")
	f.orgID, f.userID, f.agentID = seed.orgID, seed.userID, seed.agentID
}

// seedTenantNamed creates one org, user and agent with a unique slug.
func (f *tenancyFixture) seedTenantNamed(ctx context.Context, slug string) tenantSeed {
	f.t.Helper()
	var seed tenantSeed
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.organizations (name, slug)
		VALUES ($1, $1) RETURNING id::text`, slug).Scan(&seed.orgID); err != nil {
		f.t.Fatalf("seed org %s: %v", slug, err)
	}
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.users (org_id, email, name)
		VALUES ($1::uuid, $2, $3) RETURNING id::text`,
		seed.orgID, slug+"@example.com", slug).Scan(&seed.userID); err != nil {
		f.t.Fatalf("seed user %s: %v", slug, err)
	}
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.agents (org_id, created_by, name, slug)
		VALUES ($1::uuid, $2::uuid, $3, $3) RETURNING id::text`,
		seed.orgID, seed.userID, slug).Scan(&seed.agentID); err != nil {
		f.t.Fatalf("seed agent %s: %v", slug, err)
	}
	return seed
}

// seedToken creates a token for the primary tenant.
func (f *tenancyFixture) seedToken(ctx context.Context, seed tokenSeed) string {
	f.t.Helper()
	return f.seedTokenFor(ctx, f.orgID, seed)
}

// withRole runs fn in a transaction as the spec's role, setting the org GUC
// only when spec.orgGUC is non-nil.
func (f *tenancyFixture) withRole(ctx context.Context, spec roleSpec, fn func(*sql.Tx) error) error {
	tx, err := f.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if err := f.applyRole(ctx, tx, spec); err != nil {
		return err
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

// applyRole sets the optional role and org GUC before the callback.
func (f *tenancyFixture) applyRole(ctx context.Context, tx *sql.Tx, spec roleSpec) error {
	if spec.name == "" {
		return f.applyGUC(ctx, tx, spec.orgGUC)
	}
	if err := setRole(ctx, tx, spec.name); err != nil {
		return err
	}
	return f.applyGUC(ctx, tx, spec.orgGUC)
}

// applyGUC sets the org selector when one was supplied.
func (f *tenancyFixture) applyGUC(ctx context.Context, tx *sql.Tx, guc *string) error {
	if guc == nil {
		return nil
	}
	return f.setOrgGUC(ctx, tx, guc)
}

// setRole validates and sets one allowlisted role.
func setRole(ctx context.Context, tx *sql.Tx, name string) error {
	statement, err := roleStatement(name)
	if err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, statement); err != nil {
		return fmt.Errorf("set role %s: %w", name, err)
	}
	return nil
}

// setOrgGUC sets the transaction-local org selector.
func (f *tenancyFixture) setOrgGUC(ctx context.Context, tx *sql.Tx, value *string) error {
	if _, err := tx.ExecContext(ctx,
		`SELECT set_config('app.current_org_id', $1, true)`, *value); err != nil {
		return fmt.Errorf("set org guc: %w", err)
	}
	return nil
}

// requireSQLSTATE asserts the error is a *pq.Error with the given code.
func (f *tenancyFixture) requireSQLSTATE(err error, state sqlState) {
	f.t.Helper()
	if err == nil {
		f.t.Fatalf("expected SQLSTATE %s, got nil", state.code)
	}
	var pqErr *pq.Error
	if !errors.As(err, &pqErr) {
		f.t.Fatalf("expected *pq.Error, got %T: %v", err, err)
	}
	if string(pqErr.Code) != state.code {
		f.t.Fatalf("expected SQLSTATE %s, got %s: %v", state.code, pqErr.Code, err)
	}
}

// loadRoleFlags reads the pg_roles booleans for one role.
func (f *tenancyFixture) loadRoleFlags(ctx context.Context, spec roleSpec) roleFlags {
	f.t.Helper()
	var flags roleFlags
	if err := f.db.QueryRowContext(ctx, `
		SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit
		FROM pg_roles WHERE rolname = $1`, spec.name).
		Scan(&flags.super, &flags.bypass, &flags.login, &flags.inherit); err != nil {
		f.t.Fatalf("read role flags for %s: %v", spec.name, err)
	}
	return flags
}

// connLimit reads the connection limit for one role.
func (f *tenancyFixture) connLimit(ctx context.Context, spec roleSpec) int {
	f.t.Helper()
	var limit int
	if err := f.db.QueryRowContext(ctx,
		`SELECT rolconnlimit FROM pg_roles WHERE rolname = $1`, spec.name).Scan(&limit); err != nil {
		f.t.Fatalf("read rolconnlimit for %s: %v", spec.name, err)
	}
	return limit
}

// assertMembers checks the recursive members of a role.
func (f *tenancyFixture) assertMembers(ctx context.Context, spec membershipSpec) {
	f.t.Helper()
	rows, err := f.db.QueryContext(ctx, `
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
		ORDER BY r.rolname`, spec.role)
	if err != nil {
		f.t.Fatalf("members of %s: %v", spec.role, err)
	}
	defer rows.Close()
	requireRoleList(f.t, "members of "+spec.role, scanStrings(f.t, rows), spec.want)
}

// assertDirectMembers checks the roles granted directly to spec.role, without
// recursion. A recursive walk of ibex_auth also returns ibex_runtime and
// ibex_worker, because those are members of the ibex_app membership it holds,
// so "no membership other than ibex_app" has to read the direct rows.
func (f *tenancyFixture) assertDirectMembers(ctx context.Context, spec membershipSpec) {
	f.t.Helper()
	rows, err := f.db.QueryContext(ctx, `
		SELECT granted.rolname
		FROM pg_auth_members am
		JOIN pg_roles granted ON granted.oid = am.roleid
		JOIN pg_roles member ON member.oid = am.member
		WHERE member.rolname = $1
		ORDER BY granted.rolname`, spec.role)
	if err != nil {
		f.t.Fatalf("direct members of %s: %v", spec.role, err)
	}
	defer rows.Close()
	requireRoleList(f.t, "direct members of "+spec.role, scanStrings(f.t, rows), spec.want)
}

// requireRoleList compares two ordered role name lists.
func requireRoleList(t *testing.T, label string, got, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s = %v, want %v", label, got, want)
	}
	for i := range got {
		if got[i] != want[i] {
			t.Fatalf("%s = %v, want %v", label, got, want)
		}
	}
}

// assertNoMemberships checks a role holds no membership of its own.
func (f *tenancyFixture) assertNoMemberships(ctx context.Context, spec roleSpec) {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = $1)`,
		spec.name).Scan(&n); err != nil {
		f.t.Fatalf("memberships of %s: %v", spec.name, err)
	}
	if n != 0 {
		f.t.Fatalf("%s must hold no membership, got %d", spec.name, n)
	}
}

// scanStrings collects a single text column from rows.
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

// roleCount counts how many of the set's roles exist.
func (f *tenancyFixture) roleCount(ctx context.Context, set roleSet) int {
	f.t.Helper()
	var n int
	if err := f.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM pg_roles WHERE rolname = ANY($1)`, pq.Array(set.names)).Scan(&n); err != nil {
		f.t.Fatalf("pg_roles count: %v", err)
	}
	return n
}

// assertConnLimit checks one role's connection limit.
func (f *tenancyFixture) assertConnLimit(ctx context.Context, check connLimitCheck) {
	f.t.Helper()
	if got := f.connLimit(ctx, check.spec); got != check.want {
		f.t.Fatalf("%s rolconnlimit = %d, want %d", check.spec.name, got, check.want)
	}
}

// indexExists reports whether a schema-qualified index exists.
func (f *tenancyFixture) indexExists(ctx context.Context, index indexName) bool {
	f.t.Helper()
	var exists bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT to_regclass($1) IS NOT NULL`, index.qualified).Scan(&exists); err != nil {
		f.t.Fatalf("to_regclass %s: %v", index.qualified, err)
	}
	return exists
}

// assertVersion checks the migration version and dirty flag.
func (f *tenancyFixture) assertVersion(ctx context.Context, check versionCheck) {
	f.t.Helper()
	version, dirty, err := Version(f.dsn)
	if err != nil {
		f.t.Fatalf("version: %v", err)
	}
	if dirty {
		f.t.Fatal("expected clean migration state")
	}
	if version != check.want {
		f.t.Fatalf("version = %d, want %d", version, check.want)
	}
}
