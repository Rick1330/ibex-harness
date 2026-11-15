//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"slices"
	"strings"
	"testing"

	"github.com/lib/pq"
)

// readerGrant is one row of the function→role EXECUTE matrix: the function's
// signature and the only capability roles allowed to execute it.
type readerGrant struct {
	name      string
	signature string
	allowed   []string
}

// capabilityRoles is every least-privilege login plus the two NOLOGIN roles, so
// a grant that leaks to one of them fails the matrix instead of being missed.
var capabilityRoles = []string{
	"ibex_app", "ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_purge", "ibex_auth",
}

// bootstrapDefiners are the six SECURITY DEFINER functions 000069 creates. The
// default model policy has no definer of its own: it is written by
// bootstrap_upsert_organization, in the statement that creates the organization.
// They are on this matrix for the same reason the five readers are: EXECUTE on a
// definer that runs as `ibex_service` is a capability, so it must be granted to
// exactly one role.
var bootstrapDefiners = []string{
	"ibex_core.bootstrap_upsert_organization(uuid, text, text)",
	"ibex_core.bootstrap_lock_organization(uuid)",
	"ibex_core.bootstrap_lookup_subjects(uuid)",
	"ibex_core.bootstrap_create_identity(uuid, uuid, text, text, uuid, text, text)",
	"ibex_core.bootstrap_insert_pat(uuid, uuid, uuid, uuid, text, text, text, bigint)",
	"ibex_core.bootstrap_upsert_service_token(uuid, text, text, bigint)",
}

// bootstrapDefinerGrants is the matrix rows for the six definers: only
// ibex_bootstrap may execute them.
func bootstrapDefinerGrants() []readerGrant {
	grants := make([]readerGrant, 0, len(bootstrapDefiners))
	for _, signature := range bootstrapDefiners {
		grants = append(grants, readerGrant{
			name: signature, signature: signature, allowed: []string{"ibex_bootstrap"},
		})
	}
	return grants
}

// readerGrants is the complete function→role grant matrix.
func readerGrants() []readerGrant {
	return append([]readerGrant{
		{"auth token lookup", "ibex_core.auth_find_token_by_prefix(text)", []string{"ibex_auth"}},
		{"rate-limit snapshot", "ibex_core.rate_limit_overrides_snapshot()", []string{"ibex_runtime"}},
		{"session sweep", "ibex_core.sessions_abandon_idle(timestamptz, integer)", []string{"ibex_runtime"}},
		{"budget sweep", "ibex_core.budget_reservations_expire_stale(interval, integer)", []string{"ibex_worker"}},
		{"active periods", "ibex_billing.active_periods()", []string{"ibex_worker"}},
	}, bootstrapDefinerGrants()...)
}

// grantQuery is a role and a function signature for a privilege check.
type grantQuery struct {
	role, signature string
}

// functionRef is a function signature for a PUBLIC privilege check.
type functionRef struct {
	signature string
}

// readerSeeds holds the two tenants and the rows the snapshot tests consume.
type readerSeeds struct {
	a, b                tenantSeed
	periodA, periodB    string
	claimedReservationA string
}

// TestTenancyReaderGrantMatrix asserts each function is executable by exactly
// the intended role and never by PUBLIC.
func TestTenancyReaderGrantMatrix(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, grant := range readerGrants() {
		t.Run(grant.name, func(t *testing.T) {
			assertReaderGrants(f.sub(t), ctx, grant)
		})
	}
}

// assertReaderGrants checks every capability role and PUBLIC for one function.
func assertReaderGrants(f *tenancyFixture, ctx context.Context, grant readerGrant) {
	f.t.Helper()
	for _, role := range capabilityRoles {
		want := slices.Contains(grant.allowed, role)
		query := grantQuery{role: role, signature: grant.signature}
		if got := f.hasFunctionPrivilege(ctx, query); got != want {
			f.t.Fatalf("%s EXECUTE on %s = %v, want %v", role, grant.signature, got, want)
		}
	}
	if f.publicCanExecute(ctx, functionRef{signature: grant.signature}) {
		f.t.Fatalf("PUBLIC must not execute %s", grant.signature)
	}
}

// definerAttribute is the owner and pinned search_path of one definer.
type definerAttribute struct {
	owner, searchPath string
	definer           bool
}

// TestTenancyBootstrapDefinerAttributes asserts every bootstrap definer is
// owned by ibex_service, is SECURITY DEFINER, and pins search_path.
//
// A CREATE OR REPLACE that forgets ALTER OWNER leaves the function owned by
// whoever ran the migration — a superuser — and the definer then runs with
// BYPASSRLS and full table rights. The grant matrix cannot see that: the
// privilege still belongs to ibex_bootstrap. The owner and proconfig checks are
// what makes that mistake fail CI.
func TestTenancyBootstrapDefinerAttributes(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, signature := range bootstrapDefiners {
		attributes := f.loadDefinerAttributes(ctx, functionRef{signature: signature})
		if attributes.owner != "ibex_service" {
			t.Fatalf("%s owner = %s, want ibex_service", signature, attributes.owner)
		}
		if !attributes.definer {
			t.Fatalf("%s is not SECURITY DEFINER", signature)
		}
		if attributes.searchPath != "search_path=ibex_core, pg_temp" {
			t.Fatalf("%s proconfig = %q, want the pinned search_path", signature, attributes.searchPath)
		}
	}
}

// loadDefinerAttributes reads owner, security mode and the search_path pin.
func (f *tenancyFixture) loadDefinerAttributes(ctx context.Context, ref functionRef) definerAttribute {
	f.t.Helper()
	var attributes definerAttribute
	var config []string
	if err := f.db.QueryRowContext(ctx, `
		SELECT pg_get_userbyid(p.proowner), p.prosecdef, COALESCE(p.proconfig, '{}'::text[])
		FROM pg_proc p
		WHERE p.oid = $1::regprocedure`, ref.signature).
		Scan(&attributes.owner, &attributes.definer, pq.Array(&config)); err != nil {
		f.t.Fatalf("definer attributes for %s: %v", ref.signature, err)
	}
	for _, entry := range config {
		if strings.HasPrefix(entry, "search_path=") {
			attributes.searchPath = entry
		}
	}
	return attributes
}

// hasFunctionPrivilege checks one role's EXECUTE privilege.
func (f *tenancyFixture) hasFunctionPrivilege(ctx context.Context, query grantQuery) bool {
	f.t.Helper()
	var allowed bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT has_function_privilege($1::name, $2::regprocedure, 'EXECUTE')`,
		query.role, query.signature).Scan(&allowed); err != nil {
		f.t.Fatalf("privilege %s on %s: %v", query.role, query.signature, err)
	}
	return allowed
}

// publicCanExecute reports whether PUBLIC holds EXECUTE on a function.
func (f *tenancyFixture) publicCanExecute(ctx context.Context, ref functionRef) bool {
	f.t.Helper()
	var allowed bool
	if err := f.db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM pg_proc p,
			     aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl
			WHERE p.oid = $1::regprocedure
			  AND acl.grantee = 0
			  AND acl.privilege_type = 'EXECUTE'
		)`, ref.signature).Scan(&allowed); err != nil {
		f.t.Fatalf("PUBLIC privilege on %s: %v", ref.signature, err)
	}
	return allowed
}

// TestTenancySessionSweepBounds rejects a future cutoff that could abandon every
// tenant's live sessions.
func TestTenancySessionSweepBounds(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	err := f.withRole(ctx, role("ibex_runtime"), func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`SELECT * FROM ibex_core.sessions_abandon_idle(NOW() + interval '1 hour', 10)`)
		return err
	})
	f.requireSQLSTATE(err, sqlState{code: "22023"})
	err = f.withRole(ctx, role("ibex_runtime"), func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`SELECT * FROM ibex_core.sessions_abandon_idle(NOW() - interval '30 minutes', 10)`)
		return err
	})
	if err != nil {
		t.Fatalf("past cutoff should succeed: %v", err)
	}
}

// TestTenancySnapshotReaders seeds two tenants and consumes the reader results.
func TestTenancySnapshotReaders(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	seeds := f.seedReaderRows(ctx)
	assertRateLimitSnapshot(t, f, ctx, seeds)
	assertActivePeriods(t, f, ctx, seeds)
	assertBudgetSweep(t, f, ctx, seeds)
}

// periodSeed is one active budget period to seed.
type periodSeed struct {
	orgID    string
	capCents int
}

// reservationSeed is one claimed budget reservation to seed.
type readerReservationSeed struct {
	tenant   tenantSeed
	periodID string
}

// seedReaderRows creates two tenants, rate limits, active periods and one
// claimed reservation for tenant A.
func (f *tenancyFixture) seedReaderRows(ctx context.Context) readerSeeds {
	f.t.Helper()
	f.seedTenant(ctx)
	seeds := readerSeeds{
		a: tenantSeed{orgID: f.orgID, userID: f.userID, agentID: f.agentID},
		b: f.seedTenantNamed(ctx, "other-org"),
	}
	f.insertRateLimits(ctx, seeds)
	seeds.periodA = f.insertPeriod(ctx, periodSeed{orgID: seeds.a.orgID, capCents: 100})
	seeds.periodB = f.insertPeriod(ctx, periodSeed{orgID: seeds.b.orgID, capCents: 200})
	seeds.claimedReservationA = f.insertClaimedReservation(ctx, readerReservationSeed{tenant: seeds.a, periodID: seeds.periodA})
	return seeds
}

// insertRateLimits adds one org-level override per tenant.
func (f *tenancyFixture) insertRateLimits(ctx context.Context, seeds readerSeeds) {
	f.t.Helper()
	if _, err := f.db.ExecContext(ctx, `
		INSERT INTO ibex_core.rate_limit_overrides (org_id, agent_id, requests_per_minute)
		VALUES ($1::uuid, NULL, 10), ($2::uuid, NULL, 20)`,
		seeds.a.orgID, seeds.b.orgID); err != nil {
		f.t.Fatalf("seed rate limits: %v", err)
	}
}

// insertPeriod adds one currently-active budget period and returns its id.
func (f *tenancyFixture) insertPeriod(ctx context.Context, seed periodSeed) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_billing.budget_periods (org_id, period_start, period_end, cap_cents)
		VALUES ($1::uuid, NOW() - interval '1 day', NOW() + interval '1 day', $2)
		RETURNING id::text`, seed.orgID, seed.capCents).Scan(&id); err != nil {
		f.t.Fatalf("seed period: %v", err)
	}
	return id
}

// insertClaimedReservation adds one stale claimed reservation and returns its id.
func (f *tenancyFixture) insertClaimedReservation(ctx context.Context, seed readerReservationSeed) string {
	f.t.Helper()
	var id string
	if err := f.db.QueryRowContext(ctx, `
		INSERT INTO ibex_core.budget_reservations
			(organization_id, agent_id, budget_period_id, reservation_key, request_hash,
			 state, amount_estimated_cents, lease_expires_at, created_at)
		VALUES ($1::uuid, $2::uuid, $3::uuid, 'reader-key', repeat('a', 64),
		        'claimed', 10, NOW() - interval '1 hour', NOW() - interval '2 hours')
		RETURNING id::text`, seed.tenant.orgID, seed.tenant.agentID, seed.periodID).Scan(&id); err != nil {
		f.t.Fatalf("seed reservation: %v", err)
	}
	return id
}

// assertRateLimitSnapshot checks the runtime reader sees both tenants.
func assertRateLimitSnapshot(t *testing.T, f *tenancyFixture, ctx context.Context, seeds readerSeeds) {
	t.Helper()
	got := map[string]int{}
	err := f.withRole(ctx, role("ibex_runtime"), func(tx *sql.Tx) error {
		rows, err := tx.QueryContext(ctx,
			`SELECT org_id::text, requests_per_minute FROM ibex_core.rate_limit_overrides_snapshot()`)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var orgID string
			var rpm int
			if err := rows.Scan(&orgID, &rpm); err != nil {
				return err
			}
			got[orgID] = rpm
		}
		return rows.Err()
	})
	if err != nil {
		t.Fatalf("rate-limit snapshot: %v", err)
	}
	if got[seeds.a.orgID] != 10 {
		t.Fatalf("tenant A rpm = %d, want 10", got[seeds.a.orgID])
	}
	if got[seeds.b.orgID] != 20 {
		t.Fatalf("tenant B rpm = %d, want 20", got[seeds.b.orgID])
	}
}

// assertActivePeriods checks the worker reader sees both active periods.
func assertActivePeriods(t *testing.T, f *tenancyFixture, ctx context.Context, seeds readerSeeds) {
	t.Helper()
	seen := map[string]bool{}
	err := f.withRole(ctx, role("ibex_worker"), func(tx *sql.Tx) error {
		rows, err := tx.QueryContext(ctx, `SELECT org_id::text FROM ibex_billing.active_periods()`)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			var orgID string
			if err := rows.Scan(&orgID); err != nil {
				return err
			}
			seen[orgID] = true
		}
		return rows.Err()
	})
	if err != nil {
		t.Fatalf("active periods: %v", err)
	}
	if !seen[seeds.a.orgID] || !seen[seeds.b.orgID] {
		t.Fatalf("active periods saw %v, want both tenants", seen)
	}
}

// assertBudgetSweep checks the persisted effect of the stale-lease sweep.
func assertBudgetSweep(t *testing.T, f *tenancyFixture, ctx context.Context, seeds readerSeeds) {
	t.Helper()
	expired, err := f.expireStaleReservations(ctx)
	if err != nil {
		t.Fatalf("budget sweep: %v", err)
	}
	if len(expired) != 1 {
		t.Fatalf("expired %d reservations, want 1", len(expired))
	}
	if expired[0] != seeds.claimedReservationA {
		t.Fatalf("expired %s, want %s", expired[0], seeds.claimedReservationA)
	}
	assertReservationExpired(t, f, ctx, seeds.claimedReservationA)
}

// expireStaleReservations runs the worker sweep and returns the expired ids.
func (f *tenancyFixture) expireStaleReservations(ctx context.Context) ([]string, error) {
	var expired []string
	err := f.withRole(ctx, role("ibex_worker"), func(tx *sql.Tx) error {
		rows, err := tx.QueryContext(ctx,
			`SELECT expired::text FROM ibex_core.budget_reservations_expire_stale(interval '0', 10) AS expired`)
		if err != nil {
			return err
		}
		defer rows.Close()
		expired = scanStrings(f.t, rows)
		return nil
	})
	return expired, err
}

// assertReservationExpired checks the persisted state and version bump.
func assertReservationExpired(t *testing.T, f *tenancyFixture, ctx context.Context, id string) {
	t.Helper()
	var state string
	var leaseCleared bool
	var version int
	if err := f.db.QueryRowContext(ctx, `
		SELECT state, lease_expires_at IS NULL, version
		FROM ibex_core.budget_reservations WHERE id = $1::uuid`,
		id).Scan(&state, &leaseCleared, &version); err != nil {
		t.Fatalf("read reservation: %v", err)
	}
	if state != "expired" {
		t.Fatalf("reservation state = %s, want expired", state)
	}
	if !leaseCleared {
		t.Fatal("reservation lease was not cleared")
	}
	if version != 2 {
		t.Fatalf("reservation version = %d, want 2", version)
	}
}

// TestTenancyBudgetSweepValidation rejects a negative grace and a zero batch.
func TestTenancyBudgetSweepValidation(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, query := range []string{
		`SELECT * FROM ibex_core.budget_reservations_expire_stale(interval '-1 second', 10)`,
		`SELECT * FROM ibex_core.budget_reservations_expire_stale(interval '0', 0)`,
	} {
		err := f.withRole(ctx, role("ibex_worker"), func(tx *sql.Tx) error {
			_, err := tx.ExecContext(ctx, query)
			return err
		})
		f.requireSQLSTATE(err, sqlState{code: "22023"})
	}
}

// ================================================================
// Capability login matrix
//
// The function→role matrix above answers "who may execute what". The cases
// below answer the other half of the service role model, because the v1 profile
// moves every app service off the owner login onto a capability login: each
// identity is NOBYPASSRLS and unprivileged, each login holds exactly the
// memberships it needs, no login can read a tenant table without SET ROLE, and
// every definer a login calls still resolves. Any one of those regressing turns
// the per-connection role pin into decoration, which is why they are asserted
// against the catalogue rather than trusted to the migration comments.
// ================================================================

// capabilityIdentities is every role that carries a capability in the model:
// the four LOGIN roles a process connects as, plus the three NOLOGIN identities
// they act through (the purge saga, the service-owned definers and the evidence
// relay). A privilege that leaks to a NOLOGIN identity is still a privilege a
// caller can reach with SET ROLE, so all seven are on the attribute matrix.
var capabilityIdentities = []string{
	"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_auth",
	"ibex_purge", "ibex_service", "ibex_evidence_relay",
}

// capabilityLogins is the LOGIN subset: the roles a process in the v1 profile
// connects as, and the only roles the table-grant denial applies to. ibex_purge
// and ibex_service are excluded on purpose — the purge saga and the definer
// bodies hold deliberate column-scoped grants, and they are reached only
// through SET ROLE.
var capabilityLogins = []string{"ibex_runtime", "ibex_worker", "ibex_bootstrap", "ibex_auth"}

// capabilityFlags are the pg_roles privilege flags a capability identity must
// hold false. loadRoleFlags covers super and bypass for the role tests; the two
// CREATE flags are read here because no existing helper exposes them against a
// *sql.DB.
type capabilityFlags struct {
	super, bypass, createRole, createDB bool
}

// capabilityAttributeCase is one privilege flag plus the consequence of it being
// set. The consequence is part of the failure message: the assertion protects
// the isolation claim, so a failure has to say what the claim loses.
type capabilityAttributeCase struct {
	name string
	read func(capabilityFlags) bool
	risk string
}

// capabilityAttributeCases is the attribute half of the model. Every row is a
// privilege no capability identity may hold: 000064, 000036 and 000063 create
// their roles with all four false, and no migration deliberately grants
// CREATEROLE or CREATEDB to a capability identity. If one ever does, this table
// is where the exception has to be recorded, with its reason.
func capabilityAttributeCases() []capabilityAttributeCase {
	return []capabilityAttributeCase{
		{"rolbypassrls", func(flags capabilityFlags) bool { return flags.bypass },
			"RLS is skipped on every table, so the SET ROLE pin stops constraining anything"},
		{"rolsuper", func(flags capabilityFlags) bool { return flags.super },
			"a superuser ignores RLS, ACLs and ownership at once"},
		{"rolcreaterole", func(flags capabilityFlags) bool { return flags.createRole },
			"it can mint a role and grant itself the service identity"},
		{"rolcreatedb", func(flags capabilityFlags) bool { return flags.createDB },
			"it can create a database outside the migrated, policy-guarded set"},
	}
}

// TestTenancyCapabilityRoleAttributes asserts every capability identity is
// NOBYPASSRLS, is not a superuser, and holds neither CREATE flag.
func TestTenancyCapabilityRoleAttributes(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, name := range capabilityIdentities {
		flags := f.loadCapabilityFlags(ctx, name)
		for _, attribute := range capabilityAttributeCases() {
			t.Run(name+"/"+attribute.name, func(t *testing.T) {
				if attribute.read(flags) {
					t.Fatalf("%s %s = true, want false: %s", name, attribute.name, attribute.risk)
				}
			})
		}
	}
}

// loadCapabilityFlags reads the four privilege flags for one role. A missing
// role fails here (sql.ErrNoRows) instead of passing silently.
func (f *tenancyFixture) loadCapabilityFlags(ctx context.Context, name string) capabilityFlags {
	f.t.Helper()
	var flags capabilityFlags
	if err := f.db.QueryRowContext(ctx, `
		SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
		FROM pg_roles WHERE rolname = $1`, name).
		Scan(&flags.super, &flags.bypass, &flags.createRole, &flags.createDB); err != nil {
		f.t.Fatalf("read privilege flags for %s: %v", name, err)
	}
	return flags
}

// capabilityMemberships is the membership half of the model, read from the
// migrations rather than assumed: 000064 grants ibex_app to the runtime and
// worker logins and ibex_purge to the worker, 000068 grants ibex_app to the
// auth login, and ibex_bootstrap is created with no membership at all. The rows
// are the direct pg_auth_members rows; every capability role is NOINHERIT, so a
// membership is usable only through SET ROLE.
func capabilityMemberships() []membershipSpec {
	return []membershipSpec{
		{role: "ibex_runtime", want: []string{"ibex_app"}},
		{role: "ibex_worker", want: []string{"ibex_app", "ibex_purge"}},
		{role: "ibex_auth", want: []string{"ibex_app"}},
		{role: "ibex_bootstrap"},
	}
}

// serviceMemberDenials is every role 000064 and 000068 explicitly revoke
// ibex_service from. The migrations do not rely on absence — a future GRANT
// must not be able to turn a tenant identity into the service identity
// silently — and this is the assertion that those revocations landed.
var serviceMemberDenials = []string{
	"ibex_app", "ibex_runtime", "ibex_worker", "ibex_bootstrap",
	"ibex_auth", "ibex_purge", "ibex_evidence_relay",
}

// TestTenancyCapabilityLoginMemberships asserts each login holds exactly the
// memberships it needs and that no capability identity reaches ibex_service.
func TestTenancyCapabilityLoginMemberships(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, spec := range capabilityMemberships() {
		t.Run(spec.role, func(t *testing.T) {
			f.sub(t).assertDirectMembers(ctx, spec)
		})
	}
	for _, name := range serviceMemberDenials {
		t.Run("no service membership/"+name, func(t *testing.T) {
			if f.sub(t).isMemberOf(ctx, name, "ibex_service") {
				t.Fatalf("%s is a member of ibex_service by some path; only the owner may hold it", name)
			}
		})
	}
}

// isMemberOf reports whether member reaches grantedRole by any membership path.
// pg_has_role(..., 'MEMBER') is the recursive test, which is what this denial
// needs: a transitive path would hand a capability the service identity without
// ever creating a direct row the direct-membership matrix could see.
func (f *tenancyFixture) isMemberOf(ctx context.Context, member, grantedRole string) bool {
	f.t.Helper()
	var isMember bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT pg_has_role($1::name, $2::name, 'MEMBER')`, member, grantedRole).Scan(&isMember); err != nil {
		f.t.Fatalf("membership of %s in %s: %v", member, grantedRole, err)
	}
	return isMember
}

// tenantTableNames are the RLS-guarded tenant tables every capability login must
// reach only through SET ROLE ibex_app or a SECURITY DEFINER function. They are
// three different read paths — memory content, session rows and the idempotency
// ledger — so a grant added to any of them shows up here.
var tenantTableNames = []string{
	"ibex_core.memories",
	"ibex_core.sessions",
	"ibex_core.idempotency_ledger",
}

// tablePrivilegeQuery is one has_table_privilege check with the role named
// explicitly. Passing the role name (never current_user) is what makes the
// check independent of the login the test connection happens to use.
type tablePrivilegeQuery struct {
	role, table, privilege string
}

// TestTenancyCapabilityLoginTableGrants asserts no capability login holds a
// table-level SELECT on a tenant table, so the only path to tenant rows is SET
// ROLE ibex_app (whose grants are RLS-guarded) or a definer owned by
// ibex_service. 000064 grants these logins schema USAGE and nothing else.
//
// The ibex_app assertion is the control: it proves the privilege query resolves
// the table and the ACL, so a false result for a login is a real denial rather
// than a mistyped table name. has_table_privilege reads the role's own
// privileges, which for a NOINHERIT role excludes its memberships — the same
// reason SET ROLE is required at runtime.
func TestTenancyCapabilityLoginTableGrants(t *testing.T) {
	f := newTenancyFixture(t)
	for _, table := range tenantTableNames {
		t.Run(table, func(t *testing.T) {
			assertTableGrantsFor(t, f, table)
		})
	}
}

// assertTableGrantsFor proves that the pinned role is the only path to a tenant
// table: ibex_app holds table-level SELECT, and no capability login does. A
// login that held one could read tenant rows without SET ROLE, and therefore
// without the RLS predicate.
func assertTableGrantsFor(t *testing.T, f *tenancyFixture, table string) {
	t.Helper()
	sub := f.sub(t)
	sub.assertTableSelect(t, table, "ibex_app")
	for _, login := range capabilityLogins {
		sub.assertNoTableSelect(t, table, login)
	}
}

func (f *tenancyFixture) assertTableSelect(t *testing.T, table, role string) {
	t.Helper()
	query := tablePrivilegeQuery{role: role, table: table, privilege: "SELECT"}
	if !f.hasTablePrivilege(t.Context(), query) {
		t.Fatalf("control: %s must hold table-level SELECT on %s", role, table)
	}
}

func (f *tenancyFixture) assertNoTableSelect(t *testing.T, table, role string) {
	t.Helper()
	query := tablePrivilegeQuery{role: role, table: table, privilege: "SELECT"}
	if f.hasTablePrivilege(t.Context(), query) {
		t.Fatalf("%s holds table-level SELECT on %s, want none: the only path must be SET ROLE ibex_app or a definer", role, table)
	}
}

// hasTablePrivilege checks one role's table-level privilege.
func (f *tenancyFixture) hasTablePrivilege(ctx context.Context, query tablePrivilegeQuery) bool {
	f.t.Helper()
	var allowed bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT has_table_privilege($1::name, $2, $3)`,
		query.role, query.table, query.privilege).Scan(&allowed); err != nil {
		f.t.Fatalf("privilege %s on %s: %v", query.role, query.table, err)
	}
	return allowed
}

// loginDefinerGrant is one definer a login must be able to resolve: EXECUTE on
// the function plus USAGE on the schema that qualifies its name.
type loginDefinerGrant struct {
	role, schema, signature string
}

// loginDefinerGrants is the complete login→definer resolution matrix. The
// reader matrix above proves EXECUTE; this adds the schema USAGE, because
// EXECUTE without it still fails at name resolution with 42501 and the login
// cannot run at all. The bootstrap definers come from bootstrapDefiners so the
// two matrices cannot drift apart.
func loginDefinerGrants() []loginDefinerGrant {
	grants := []loginDefinerGrant{
		{"ibex_auth", "ibex_core", "ibex_core.auth_find_token_by_prefix(text)"},
		{"ibex_runtime", "ibex_core", "ibex_core.rate_limit_overrides_snapshot()"},
		{"ibex_runtime", "ibex_core", "ibex_core.sessions_abandon_idle(timestamptz, integer)"},
		{"ibex_worker", "ibex_billing", "ibex_billing.active_periods()"},
		{"ibex_worker", "ibex_core", "ibex_core.budget_reservations_expire_stale(interval, integer)"},
	}
	for _, signature := range bootstrapDefiners {
		grants = append(grants, loginDefinerGrant{"ibex_bootstrap", "ibex_core", signature})
	}
	return grants
}

// TestTenancyCapabilityDefinerResolution asserts each login can execute the
// definers it needs and resolve their schema-qualified names.
func TestTenancyCapabilityDefinerResolution(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, grant := range loginDefinerGrants() {
		t.Run(grant.role+"/"+grant.signature, func(t *testing.T) {
			assertLoginDefinerResolves(f.sub(t), ctx, grant)
		})
	}
}

// assertLoginDefinerResolves checks EXECUTE and the schema USAGE behind it.
func assertLoginDefinerResolves(f *tenancyFixture, ctx context.Context, grant loginDefinerGrant) {
	f.t.Helper()
	if !f.hasFunctionPrivilege(ctx, grantQuery{role: grant.role, signature: grant.signature}) {
		f.t.Fatalf("%s cannot EXECUTE %s", grant.role, grant.signature)
	}
	var usage bool
	if err := f.db.QueryRowContext(ctx,
		`SELECT has_schema_privilege($1::name, $2, 'USAGE')`,
		grant.role, grant.schema).Scan(&usage); err != nil {
		f.t.Fatalf("schema USAGE %s on %s: %v", grant.role, grant.schema, err)
	}
	if !usage {
		f.t.Fatalf("%s lacks USAGE on schema %s, so %s does not resolve", grant.role, grant.schema, grant.signature)
	}
}
