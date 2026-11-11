//go:build integration

package postgres

import (
	"context"
	"database/sql"
	"testing"
)

// readerGrant is one row of the function→role EXECUTE matrix.
type readerGrant struct {
	name      string
	signature string
	runtime   bool
	worker    bool
	bootstrap bool
	purge     bool
	auth      bool
}

// readerGrants is the complete reader grant matrix.
var readerGrants = []readerGrant{
	{"auth token lookup", "ibex_core.auth_find_token_by_prefix(text)", false, false, false, false, true},
	{"rate-limit snapshot", "ibex_core.rate_limit_overrides_snapshot()", true, false, false, false, false},
	{"session sweep", "ibex_core.sessions_abandon_idle(timestamptz, integer)", true, false, false, false, false},
	{"budget sweep", "ibex_core.budget_reservations_expire_stale(interval, integer)", false, true, false, false, false},
	{"active periods", "ibex_billing.active_periods()", false, true, false, false, false},
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

// TestTenancyReaderGrantMatrix asserts each reader is executable by exactly the
// intended role and never by PUBLIC.
func TestTenancyReaderGrantMatrix(t *testing.T) {
	f := newTenancyFixture(t)
	ctx := t.Context()
	for _, grant := range readerGrants {
		t.Run(grant.name, func(t *testing.T) {
			sub := *f
			sub.t = t
			assertReaderGrants(&sub, ctx, grant)
		})
	}
}

// assertReaderGrants checks the five capability roles and PUBLIC for one reader.
func assertReaderGrants(f *tenancyFixture, ctx context.Context, grant readerGrant) {
	f.t.Helper()
	checks := []struct {
		role string
		want bool
	}{
		{"ibex_runtime", grant.runtime},
		{"ibex_worker", grant.worker},
		{"ibex_bootstrap", grant.bootstrap},
		{"ibex_purge", grant.purge},
		{"ibex_auth", grant.auth},
	}
	for _, check := range checks {
		query := grantQuery{role: check.role, signature: grant.signature}
		if got := f.hasFunctionPrivilege(ctx, query); got != check.want {
			f.t.Fatalf("%s EXECUTE on %s = %v, want %v", check.role, grant.signature, got, check.want)
		}
	}
	if f.publicCanExecute(ctx, functionRef{signature: grant.signature}) {
		f.t.Fatalf("PUBLIC must not execute %s", grant.signature)
	}
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
