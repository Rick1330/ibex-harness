//go:build integration

package idempotency

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/google/uuid"

	_ "github.com/lib/pq" // PostgreSQL driver for real-ledger integration tests
)

const defaultLedgerDSN = "postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable"

func ledgerDSN() string {
	if dsn := os.Getenv("POSTGRES_TEST_DSN"); dsn != "" {
		return dsn
	}
	return defaultLedgerDSN
}

func openLedgerDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", ledgerDSN())
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Skipf("postgres not available: %v", err)
	}
	if err := migratepg.Up(ledgerDSN()); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return db
}

// seedPrincipal inserts an org + agent under the service-account RLS scope and
// returns the principal plus a second principal in a different org.
func seedPrincipal(t *testing.T, db *sql.DB) (Principal, Principal) {
	t.Helper()
	ctx := context.Background()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.is_service_account', 'true', true)`); err != nil {
		t.Fatalf("set service account: %v", err)
	}
	seed := func() Principal {
		suffix := uuid.NewString()
		var orgID, agentID uuid.UUID
		if err := tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id`,
			"ledger-it", "ledger-it-"+suffix,
		).Scan(&orgID); err != nil {
			t.Fatalf("insert org: %v", err)
		}
		if err := tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.agents (org_id, name, slug) VALUES ($1, $2, $3) RETURNING id`,
			orgID, "ledger-it-agent", "ledger-it-agent-"+suffix,
		).Scan(&agentID); err != nil {
			t.Fatalf("insert agent: %v", err)
		}
		return Principal{OrgID: orgID, AgentID: agentID}
	}
	a, b := seed(), seed()
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}
	return a, b
}

// withAppRole runs fn inside a transaction that assumes the non-superuser
// ibex_app role, so FORCE RLS actually applies. The test DSN connects as the
// superuser (which bypasses RLS), mirroring
// infra/migrations/postgres/migrate_integration_test.go and
// packages/evidenceoutbox/store_rls_integration_test.go.
func withAppRole(ctx context.Context, db *sql.DB, orgID uuid.UUID, fn func(*sql.Tx) error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.ExecContext(ctx, `SET LOCAL ROLE ibex_app`); err != nil {
		return fmt.Errorf("set role ibex_app: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, orgID.String()); err != nil {
		return fmt.Errorf("set org: %w", err)
	}
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func newTestLedger(t *testing.T, db *sql.DB, lease time.Duration) *PostgresLedger {
	t.Helper()
	ledger, err := NewPostgresLedger(db, lease)
	if err != nil {
		t.Fatalf("new ledger: %v", err)
	}
	return ledger
}

// ledgerFixture bundles the per-test subject (ledger plus the org/agent
// principal) with assertion helpers, so each test reads as a sequence of
// intent-revealing calls and no helper needs a long argument list.
type ledgerFixture struct {
	t      *testing.T
	ledger *PostgresLedger
	org    Principal
}

func newLedgerFixture(t *testing.T, lease time.Duration) ledgerFixture {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	return ledgerFixture{t: t, ledger: newTestLedger(t, db, lease), org: p}
}

func newLedgerFixtureFor(t *testing.T, db *sql.DB, org Principal, lease time.Duration) ledgerFixture {
	return ledgerFixture{t: t, ledger: newTestLedger(t, db, lease), org: org}
}

func (f ledgerFixture) claim(key, hash string) ClaimOutcome {
	f.t.Helper()
	out, err := f.ledger.Claim(context.Background(), f.org, key, hash)
	if err != nil {
		f.t.Fatalf("claim %q: %v", key, err)
	}
	return out
}

func (f ledgerFixture) finalize(claim ClaimToken, status int, body string) {
	f.t.Helper()
	if err := f.ledger.Finalize(context.Background(), claim, status, []byte(body)); err != nil {
		f.t.Fatalf("finalize: %v", err)
	}
}

func (f ledgerFixture) release(claim ClaimToken) {
	f.t.Helper()
	if err := f.ledger.Release(context.Background(), claim); err != nil {
		f.t.Fatalf("release: %v", err)
	}
}

func (f ledgerFixture) requireKind(got ClaimOutcome, want ClaimKind) {
	f.t.Helper()
	if got.Kind != want {
		f.t.Fatalf("kind = %q, want %q", got.Kind, want)
	}
}

func (f ledgerFixture) requireReplay(got ClaimOutcome, status int, body string) {
	f.t.Helper()
	f.requireKind(got, ClaimReplay)
	if got.Status != status {
		f.t.Fatalf("status = %d, want %d", got.Status, status)
	}
	if string(got.Response) != body {
		f.t.Fatalf("response = %q, want %q", got.Response, body)
	}
}

func (f ledgerFixture) requireConflict(err error) {
	f.t.Helper()
	if !errors.Is(err, ErrLedgerConflict) {
		f.t.Fatalf("err = %v, want ErrLedgerConflict", err)
	}
}

func TestIntegration_PostgresLedger_ClaimFinalizeReplay(t *testing.T) {
	f := newLedgerFixture(t, 2*time.Minute)
	hash := HashRequest([]byte(`{"body":"a"}`))

	claim := f.claim("k-finalize", hash)
	f.requireKind(claim, ClaimOwned)
	f.finalize(claim.Claim, 201, `{"id":"m1"}`)

	f.requireReplay(f.claim("k-finalize", hash), 201, `{"id":"m1"}`)
	f.requireConflict(f.ledger.Finalize(context.Background(), claim.Claim, 201, []byte(`{"id":"m1"}`)))
}

func TestIntegration_PostgresLedger_ConflictOnDifferentHash(t *testing.T) {
	f := newLedgerFixture(t, 2*time.Minute)

	f.claim("k-conflict", HashRequest([]byte("a")))
	f.requireKind(f.claim("k-conflict", HashRequest([]byte("b"))), ClaimConflict)
}

func TestIntegration_PostgresLedger_InProgressThenReclaimFencesStaleOwner(t *testing.T) {
	f := newLedgerFixture(t, 150*time.Millisecond)
	hash := HashRequest([]byte("a"))

	first := f.claim("k-lease", hash)
	active := f.claim("k-lease", hash)
	if active.Kind != ClaimInProgress || active.RetryAfter <= 0 {
		t.Fatalf("active = %+v, want in_progress with retry_after", active)
	}

	time.Sleep(250 * time.Millisecond)
	reclaimed := f.claim("k-lease", hash)
	f.requireKind(reclaimed, ClaimOwned)
	if reclaimed.Claim.Version <= first.Claim.Version {
		t.Fatalf("reclaim version = %d, want > %d", reclaimed.Claim.Version, first.Claim.Version)
	}
	f.requireConflict(f.ledger.Finalize(context.Background(), first.Claim, 200, []byte("stale")))
	f.finalize(reclaimed.Claim, 200, "fresh")
}

func TestIntegration_PostgresLedger_ReleaseAndStaleRelease(t *testing.T) {
	f := newLedgerFixture(t, 2*time.Minute)
	hash := HashRequest([]byte("a"))

	claim := f.claim("k-release", hash)
	f.release(claim.Claim)
	f.requireConflict(f.ledger.Release(context.Background(), claim.Claim))

	// A released key can be claimed again as a brand new owner.
	f.requireKind(f.claim("k-release", hash), ClaimOwned)
}

func TestIntegration_PostgresLedger_RejectsInvalidClaim(t *testing.T) {
	f := newLedgerFixture(t, 2*time.Minute)
	if _, err := f.ledger.Claim(context.Background(), f.org, "", HashRequest([]byte("a"))); !errors.Is(err, ErrInvalidLedgerClaim) {
		t.Fatalf("err = %v, want ErrInvalidLedgerClaim", err)
	}
}

// assertSharedKeyVisible asserts, under ibex_app RLS, how many `shared-key`
// ledger rows are visible to orgID. The superuser DSN bypasses RLS, so the raw
// read must assume the non-superuser role to exercise the isolation policy.
func assertSharedKeyVisible(t *testing.T, db *sql.DB, orgID uuid.UUID, want int) {
	t.Helper()
	var n int
	err := withAppRole(context.Background(), db, orgID, func(tx *sql.Tx) error {
		return tx.QueryRowContext(context.Background(),
			`SELECT count(*) FROM ibex_core.idempotency_ledger WHERE dedupe_key='shared-key'`,
		).Scan(&n)
	})
	if err != nil {
		t.Fatalf("count ledger rows for org %s: %v", orgID, err)
	}
	if n != want {
		t.Fatalf("org %s row count = %d, want %d", orgID, n, want)
	}
}

// TestIntegration_PostgresLedger_RLSCrossOrgIsolation proves the ledger is
// scoped per (org, agent, key): the same key in two orgs never collides.
func TestIntegration_PostgresLedger_RLSCrossOrgIsolation(t *testing.T) {
	db := openLedgerDB(t)
	orgA, orgB := seedPrincipal(t, db)
	hash := HashRequest([]byte("same"))

	for _, org := range []Principal{orgA, orgB} {
		f := newLedgerFixtureFor(t, db, org, 2*time.Minute)
		f.requireKind(f.claim("shared-key", hash), ClaimOwned)
	}

	// A raw org-scoped read under ibex_app RLS sees exactly one row per org.
	assertSharedKeyVisible(t, db, orgA.OrgID, 1)
	assertSharedKeyVisible(t, db, orgB.OrgID, 1)
}
