//go:build integration

package postgres

import "testing"

// A2 — only the owner login carries rolsuper or rolbypassrls; the capability
// roles are never superusers and never bypass RLS.
func TestTenancyRoleAttributes(t *testing.T) {
	f := newTenancyFixture(t)
	assertOnlyOwnerPrivileged(f)
	assertCapabilityRoleAttributes(f)
}

func assertOnlyOwnerPrivileged(f *tenancyFixture) {
	f.t.Helper()
	rows, err := f.db.QueryContext(f.ctx,
		`SELECT rolname FROM pg_roles WHERE rolsuper OR rolbypassrls ORDER BY rolname`)
	if err != nil {
		f.t.Fatalf("pg_roles: %v", err)
	}
	defer rows.Close()
	if got := scanStrings(f.t, rows); len(got) != 1 || got[0] != "ibex" {
		f.t.Fatalf("expected only ibex to be superuser/BYPASSRLS, got %v", got)
	}
}

func assertCapabilityRoleAttributes(f *tenancyFixture) {
	f.t.Helper()
	for _, role := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_purge"} {
		if f.roleBool(role, "rolsuper") || f.roleBool(role, "rolbypassrls") {
			f.t.Fatalf("%s must not be superuser or BYPASSRLS", role)
		}
	}
	for _, role := range []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap"} {
		if !f.roleBool(role, "rolcanlogin") || f.roleBool(role, "rolinherit") {
			f.t.Fatalf("%s must be a NOINHERIT login", role)
		}
		f.assertConnLimit(role, 0)
	}
	if f.roleBool("ibex_purge", "rolcanlogin") {
		f.t.Fatal("ibex_purge must remain NOLOGIN")
	}
}

// A3 — recursive membership: ibex_service has exactly ibex, ibex_purge has
// exactly ibex_worker, and ibex_bootstrap holds no membership of its own.
func TestTenancyMemberships(t *testing.T) {
	f := newTenancyFixture(t)
	f.assertMembers("ibex_service", []string{"ibex"})
	f.assertMembers("ibex_purge", []string{"ibex_worker"})
	f.assertNoMemberships("ibex_bootstrap")
}
