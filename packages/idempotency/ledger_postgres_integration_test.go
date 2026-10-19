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

func claimOrFatal(t *testing.T, ledger *PostgresLedger, p Principal, key, hash string) ClaimOutcome {
	t.Helper()
	out, err := ledger.Claim(context.Background(), p, key, hash)
	if err != nil {
		t.Fatalf("claim %q: %v", key, err)
	}
	return out
}

func finalizeOrFatal(t *testing.T, ledger *PostgresLedger, claim ClaimToken, status int, body string) {
	t.Helper()
	if err := ledger.Finalize(context.Background(), claim, status, []byte(body)); err != nil {
		t.Fatalf("finalize: %v", err)
	}
}

func releaseOrFatal(t *testing.T, ledger *PostgresLedger, claim ClaimToken) {
	t.Helper()
	if err := ledger.Release(context.Background(), claim); err != nil {
		t.Fatalf("release: %v", err)
	}
}

func requireClaimKind(t *testing.T, got ClaimOutcome, want ClaimKind) {
	t.Helper()
	if got.Kind != want {
		t.Fatalf("kind = %q, want %q", got.Kind, want)
	}
}

func requireReplay(t *testing.T, got ClaimOutcome, status int, body string) {
	t.Helper()
	requireClaimKind(t, got, ClaimReplay)
	if got.Status != status {
		t.Fatalf("status = %d, want %d", got.Status, status)
	}
	if string(got.Response) != body {
		t.Fatalf("response = %q, want %q", got.Response, body)
	}
}

func requireConflict(t *testing.T, err error) {
	t.Helper()
	if !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("err = %v, want ErrLedgerConflict", err)
	}
}

func TestIntegration_PostgresLedger_ClaimFinalizeReplay(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	hash := HashRequest([]byte(`{"body":"a"}`))

	claim := claimOrFatal(t, ledger, p, "k-finalize", hash)
	requireClaimKind(t, claim, ClaimOwned)
	finalizeOrFatal(t, ledger, claim.Claim, 201, `{"id":"m1"}`)

	replay := claimOrFatal(t, ledger, p, "k-finalize", hash)
	requireReplay(t, replay, 201, `{"id":"m1"}`)
	requireConflict(t, ledger.Finalize(context.Background(), claim.Claim, 201, []byte(`{"id":"m1"}`)))
}

func TestIntegration_PostgresLedger_ConflictOnDifferentHash(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)

	claimOrFatal(t, ledger, p, "k-conflict", HashRequest([]byte("a")))
	out := claimOrFatal(t, ledger, p, "k-conflict", HashRequest([]byte("b")))
	requireClaimKind(t, out, ClaimConflict)
}

func TestIntegration_PostgresLedger_InProgressThenReclaimFencesStaleOwner(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 150*time.Millisecond)
	hash := HashRequest([]byte("a"))

	first := claimOrFatal(t, ledger, p, "k-lease", hash)
	active := claimOrFatal(t, ledger, p, "k-lease", hash)
	if active.Kind != ClaimInProgress || active.RetryAfter <= 0 {
		t.Fatalf("active = %+v, want in_progress with retry_after", active)
	}

	time.Sleep(250 * time.Millisecond)
	reclaimed := claimOrFatal(t, ledger, p, "k-lease", hash)
	requireClaimKind(t, reclaimed, ClaimOwned)
	if reclaimed.Claim.Version <= first.Claim.Version {
		t.Fatalf("reclaim version = %d, want > %d", reclaimed.Claim.Version, first.Claim.Version)
	}
	requireConflict(t, ledger.Finalize(context.Background(), first.Claim, 200, []byte("stale")))
	finalizeOrFatal(t, ledger, reclaimed.Claim, 200, "fresh")
}

func TestIntegration_PostgresLedger_ReleaseAndStaleRelease(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	hash := HashRequest([]byte("a"))

	claim := claimOrFatal(t, ledger, p, "k-release", hash)
	releaseOrFatal(t, ledger, claim.Claim)
	requireConflict(t, ledger.Release(context.Background(), claim.Claim))

	// A released key can be claimed again as a brand new owner.
	requireClaimKind(t, claimOrFatal(t, ledger, p, "k-release", hash), ClaimOwned)
}

func TestIntegration_PostgresLedger_RejectsInvalidClaim(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	if _, err := ledger.Claim(context.Background(), p, "", HashRequest([]byte("a"))); !errors.Is(err, ErrInvalidLedgerClaim) {
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
	ledger := newTestLedger(t, db, 2*time.Minute)
	hash := HashRequest([]byte("same"))

	for _, org := range []Principal{orgA, orgB} {
		requireClaimKind(t, claimOrFatal(t, ledger, org, "shared-key", hash), ClaimOwned)
	}

	// A raw org-scoped read under ibex_app RLS sees exactly one row per org.
	assertSharedKeyVisible(t, db, orgA.OrgID, 1)
	assertSharedKeyVisible(t, db, orgB.OrgID, 1)
}
