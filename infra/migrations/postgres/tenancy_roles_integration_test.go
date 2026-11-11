//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

// TestTenancyRoleAttributes asserts A2: only the owner is privileged and the
// capability roles are non-inheriting, non-bypassing logins.
func TestTenancyRoleAttributes(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	assertOnlyOwnerPrivileged(f, ctx)
	assertCapabilityRoleAttributes(f, ctx)
}

// assertOnlyOwnerPrivileged checks rolsuper and rolbypassrls are ibex-only.
func assertOnlyOwnerPrivileged(f *tenancyFixture, ctx context.Context) {
	f.t.Helper()
	rows, err := f.db.QueryContext(ctx, `
		SELECT rolname FROM pg_roles WHERE rolsuper OR rolbypassrls ORDER BY rolname`)
	if err != nil {
		f.t.Fatalf("pg_roles: %v", err)
	}
	defer rows.Close()
	if got := scanStrings(f.t, rows); len(got) != 1 || got[0] != "ibex" {
		f.t.Fatalf("expected only ibex to be superuser/BYPASSRLS, got %v", got)
	}
}

// assertCapabilityRoleAttributes checks the five capability roles.
func assertCapabilityRoleAttributes(f *tenancyFixture, ctx context.Context) {
	f.t.Helper()
	for _, name := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_purge", "ibex_auth"} {
		flags := f.loadRoleFlags(ctx, role(name))
		if flags.super || flags.bypass {
			f.t.Fatalf("%s must not be superuser or BYPASSRLS", name)
		}
	}
	for _, name := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_auth"} {
		flags := f.loadRoleFlags(ctx, role(name))
		if !flags.login || flags.inherit {
			f.t.Fatalf("%s must be a NOINHERIT login", name)
		}
		f.assertConnLimit(ctx, connLimitCheck{spec: role(name), want: 0})
	}
	if f.loadRoleFlags(ctx, role("ibex_purge")).login {
		f.t.Fatal("ibex_purge must remain NOLOGIN")
	}
}

// TestTenancyMemberships asserts A3: ibex_service has exactly ibex, ibex_purge
// has exactly ibex_worker, ibex_bootstrap holds no membership, and ibex_auth
// holds exactly its ibex_app membership.
func TestTenancyMemberships(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	f.assertMembers(ctx, membershipSpec{role: "ibex_service", want: []string{"ibex"}})
	f.assertMembers(ctx, membershipSpec{role: "ibex_purge", want: []string{"ibex_worker"}})
	f.assertNoMemberships(ctx, role("ibex_bootstrap"))
	assertAuthMemberships(f, ctx)
}

// assertAuthMemberships is the F4 lock. 000068 revokes every other capability
// from ibex_auth on the theory that absence is not a control; this asserts the
// revocation landed, so a future GRANT cannot turn the auth login into a
// second worker, purge, bootstrap, service or relay identity without failing.
func assertAuthMemberships(f *tenancyFixture, ctx context.Context) {
	f.t.Helper()
	f.assertDirectMembers(ctx, membershipSpec{role: "ibex_auth", want: []string{"ibex_app"}})
}

// authLoginFloor is the last migration before the auth login (000068).
const authLoginFloor = 67

// membershipOptions is the pg_auth_members option triple for one row.
type membershipOptions struct {
	admin, inherit, set bool
}

// TestTenancyAuthMembershipNormalized is the 000068 option lock.
//
// A plain `GRANT ibex_app TO ibex_auth` leaves an existing pg_auth_members row
// exactly as it found it (measured on PostgreSQL 16), so a login granted WITH
// ADMIN TRUE or WITH INHERIT TRUE kept those options while the migration
// reported success. The model emits ADMIN FALSE, INHERIT FALSE, SET TRUE only;
// the provenance guard tests set_option, so it admits an ADMIN row that this
// model never produces and the GRANT is what has to normalize it. Remove either
// FALSE from the GRANT and the matching case below fails.
//
// The role carries a credential on purpose: that is the provisioned re-run the
// provenance guard has to admit (a direct, SET-enabled row).
func TestTenancyAuthMembershipNormalized(t *testing.T) {
	cases := []struct {
		name  string
		grant string
		pre   membershipOptions
	}{
		{
			name:  "admin option",
			grant: "WITH ADMIN TRUE",
			pre:   membershipOptions{admin: true, set: true},
		},
		{
			name:  "inherit option",
			grant: "WITH INHERIT TRUE",
			pre:   membershipOptions{inherit: true, set: true},
		},
		{
			name:  "both options",
			grant: "WITH ADMIN TRUE, INHERIT TRUE",
			pre:   membershipOptions{admin: true, inherit: true, set: true},
		},
	}
	f := newTenancyFixture(t)
	ctx := t.Context()
	t.Cleanup(func() { resetSchema(t, f.db) })
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rewindTo(t, f, authLoginFloor)
			f.exec(ctx, `CREATE ROLE ibex_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT PASSWORD 'pre-normalization'`)
			f.exec(ctx, `GRANT ibex_app TO ibex_auth `+tc.grant)
			assertMembershipOptions(t, f, ctx, tc.pre)
			if err := Up(f.dsn); err != nil {
				t.Fatalf("up: %v", err)
			}
			assertMembershipOptions(t, f, ctx, membershipOptions{set: true})
		})
	}
}

// TestTenancyAuthMembershipCascade is the 000068 dependent-grant lock.
//
// A pre-existing `WITH ADMIN TRUE` row may have let ibex_auth grant ibex_app
// onward. Those dependent rows carry grantor = ibex_auth and are separate
// pg_auth_members rows, so normalizing the options on the ibex_auth row leaves
// them in place: the delegated role keeps the tenant identity ibex_auth handed
// it. The migration therefore has to REVOKE ADMIN OPTION ... CASCADE before the
// GRANT. Removing that revoke, or moving it after the GRANT, leaves the
// delegated row behind and fails here.
func TestTenancyAuthMembershipCascade(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	t.Cleanup(func() { resetSchema(t, f.db) })
	rewindTo(t, f, authLoginFloor)

	const delegate = "ibex_auth_delegate_probe"
	f.exec(ctx, `DROP ROLE IF EXISTS ibex_auth_delegate_probe`)
	f.exec(ctx, `CREATE ROLE ibex_auth_delegate_probe NOLOGIN`)
	// Dropping the delegate removes the dependent membership even when the
	// assertion below fails, so the next resetSchema can still drop ibex_auth.
	t.Cleanup(func() {
		execIgnoringError(context.Background(), f, []string{`DROP ROLE IF EXISTS ibex_auth_delegate_probe`})
	})

	f.exec(ctx, `CREATE ROLE ibex_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT PASSWORD 'pre-cascade'`)
	f.exec(ctx, `GRANT ibex_app TO ibex_auth WITH ADMIN TRUE, INHERIT FALSE, SET TRUE`)
	delegateApp(t, f, ctx)
	if !hasAppMembership(t, f, ctx, delegate) {
		t.Fatal("precondition: the delegated ibex_app grant is missing")
	}

	if err := Up(f.dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	if hasAppMembership(t, f, ctx, delegate) {
		t.Fatal("the delegated ibex_app grant survived the migration")
	}
	assertMembershipOptions(t, f, ctx, membershipOptions{set: true})
}

// delegateApp grants ibex_app to the fixed probe role as ibex_auth, which is
// the dependent row the migration has to withdraw. The statement is a literal
// so no role name is concatenated into SQL.
func delegateApp(t *testing.T, f *tenancyFixture, ctx context.Context) {
	t.Helper()
	if err := f.withRole(ctx, role("ibex_auth"), func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `GRANT ibex_app TO ibex_auth_delegate_probe`)
		return err
	}); err != nil {
		t.Fatalf("delegate ibex_app to the probe role: %v", err)
	}
}

// hasAppMembership reports whether member holds a direct ibex_app membership.
func hasAppMembership(t *testing.T, f *tenancyFixture, ctx context.Context, member string) bool {
	t.Helper()
	var exists bool
	if err := f.db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM pg_auth_members am
			JOIN pg_roles granted ON granted.oid = am.roleid
			JOIN pg_roles member ON member.oid = am.member
			WHERE granted.rolname = 'ibex_app' AND member.rolname = $1)`, member).Scan(&exists); err != nil {
		t.Fatalf("read membership for %s: %v", member, err)
	}
	return exists
}

// assertMembershipOptions reads ibex_auth's direct ibex_app row.
func assertMembershipOptions(t *testing.T, f *tenancyFixture, ctx context.Context, want membershipOptions) {
	t.Helper()
	var got membershipOptions
	if err := f.db.QueryRowContext(ctx, `
		SELECT am.admin_option, am.inherit_option, am.set_option
		FROM pg_auth_members am
		JOIN pg_roles granted ON granted.oid = am.roleid
		JOIN pg_roles member ON member.oid = am.member
		WHERE granted.rolname = 'ibex_app' AND member.rolname = 'ibex_auth'`).
		Scan(&got.admin, &got.inherit, &got.set); err != nil {
		t.Fatalf("read ibex_auth membership options: %v", err)
	}
	if got != want {
		t.Fatalf("ibex_auth membership options = %+v, want %+v", got, want)
	}
}
