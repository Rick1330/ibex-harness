//go:build integration

package postgres

import (
	"context"
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
