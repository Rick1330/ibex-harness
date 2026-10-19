//go:build integration

package idempotency

import (
	"context"
	"database/sql"
	"errors"
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

func newTestLedger(t *testing.T, db *sql.DB, lease time.Duration) *PostgresLedger {
	t.Helper()
	ledger, err := NewPostgresLedger(db, lease)
	if err != nil {
		t.Fatalf("new ledger: %v", err)
	}
	return ledger
}

func TestIntegration_PostgresLedger_ClaimFinalizeReplay(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	ctx := context.Background()
	hash := HashRequest([]byte(`{"body":"a"}`))

	claim, err := ledger.Claim(ctx, p, "k-finalize", hash)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if claim.Kind != ClaimOwned {
		t.Fatalf("kind = %q, want owned", claim.Kind)
	}
	if err := ledger.Finalize(ctx, claim.Claim, 201, []byte(`{"id":"m1"}`)); err != nil {
		t.Fatalf("finalize: %v", err)
	}
	replay, err := ledger.Claim(ctx, p, "k-finalize", hash)
	if err != nil {
		t.Fatalf("replay claim: %v", err)
	}
	if replay.Kind != ClaimReplay || replay.Status != 201 || string(replay.Response) != `{"id":"m1"}` {
		t.Fatalf("replay = %+v, want replay 201 body", replay)
	}
	if err := ledger.Finalize(ctx, claim.Claim, 201, []byte(`{"id":"m1"}`)); !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("second finalize err = %v, want ErrLedgerConflict", err)
	}
}

func TestIntegration_PostgresLedger_ConflictOnDifferentHash(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	ctx := context.Background()

	if _, err := ledger.Claim(ctx, p, "k-conflict", HashRequest([]byte("a"))); err != nil {
		t.Fatalf("claim: %v", err)
	}
	out, err := ledger.Claim(ctx, p, "k-conflict", HashRequest([]byte("b")))
	if err != nil {
		t.Fatalf("claim conflict: %v", err)
	}
	if out.Kind != ClaimConflict {
		t.Fatalf("kind = %q, want conflict", out.Kind)
	}
}

func TestIntegration_PostgresLedger_InProgressThenReclaimFencesStaleOwner(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 150*time.Millisecond)
	ctx := context.Background()
	hash := HashRequest([]byte("a"))

	first, err := ledger.Claim(ctx, p, "k-lease", hash)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	active, err := ledger.Claim(ctx, p, "k-lease", hash)
	if err != nil {
		t.Fatalf("active claim: %v", err)
	}
	if active.Kind != ClaimInProgress || active.RetryAfter <= 0 {
		t.Fatalf("active = %+v, want in_progress with retry_after", active)
	}

	time.Sleep(250 * time.Millisecond)
	reclaimed, err := ledger.Claim(ctx, p, "k-lease", hash)
	if err != nil {
		t.Fatalf("reclaim: %v", err)
	}
	if reclaimed.Kind != ClaimOwned || reclaimed.Claim.Version <= first.Claim.Version {
		t.Fatalf("reclaim = %+v, want owned with newer version than %d", reclaimed, first.Claim.Version)
	}
	if err := ledger.Finalize(ctx, first.Claim, 200, []byte("stale")); !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("stale finalize err = %v, want ErrLedgerConflict", err)
	}
	if err := ledger.Finalize(ctx, reclaimed.Claim, 200, []byte("fresh")); err != nil {
		t.Fatalf("fresh finalize: %v", err)
	}
}

func TestIntegration_PostgresLedger_ReleaseAndStaleRelease(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	ctx := context.Background()
	hash := HashRequest([]byte("a"))

	claim, err := ledger.Claim(ctx, p, "k-release", hash)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if err := ledger.Release(ctx, claim.Claim); err != nil {
		t.Fatalf("release: %v", err)
	}
	if err := ledger.Release(ctx, claim.Claim); !errors.Is(err, ErrLedgerConflict) {
		t.Fatalf("stale release err = %v, want ErrLedgerConflict", err)
	}
	// A released key can be claimed again as a brand new owner.
	reclaimed, err := ledger.Claim(ctx, p, "k-release", hash)
	if err != nil {
		t.Fatalf("reclaim after release: %v", err)
	}
	if reclaimed.Kind != ClaimOwned {
		t.Fatalf("kind = %q, want owned", reclaimed.Kind)
	}
}

func TestIntegration_PostgresLedger_RejectsInvalidClaim(t *testing.T) {
	db := openLedgerDB(t)
	p, _ := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	if _, err := ledger.Claim(context.Background(), p, "", HashRequest([]byte("a"))); !errors.Is(err, ErrInvalidLedgerClaim) {
		t.Fatalf("err = %v, want ErrInvalidLedgerClaim", err)
	}
}

// TestIntegration_PostgresLedger_RLSCrossOrgIsolation proves the ledger is
// scoped per (org, agent, key): the same key in two orgs never collides.
func TestIntegration_PostgresLedger_RLSCrossOrgIsolation(t *testing.T) {
	db := openLedgerDB(t)
	orgA, orgB := seedPrincipal(t, db)
	ledger := newTestLedger(t, db, 2*time.Minute)
	ctx := context.Background()
	hash := HashRequest([]byte("same"))

	claimA, err := ledger.Claim(ctx, orgA, "shared-key", hash)
	if err != nil {
		t.Fatalf("claim A: %v", err)
	}
	if claimA.Kind != ClaimOwned {
		t.Fatalf("claim A kind = %q, want owned", claimA.Kind)
	}
	claimB, err := ledger.Claim(ctx, orgB, "shared-key", hash)
	if err != nil {
		t.Fatalf("claim B: %v", err)
	}
	if claimB.Kind != ClaimOwned {
		t.Fatalf("claim B kind = %q, want owned (org-scoped row)", claimB.Kind)
	}

	// A raw org-scoped read sees exactly one row per org.
	countForOrg := func(p Principal) int {
		tx, err := db.BeginTx(ctx, nil)
		if err != nil {
			t.Fatalf("begin: %v", err)
		}
		defer func() { _ = tx.Rollback() }()
		if _, err := tx.ExecContext(ctx, `SELECT set_config('app.current_org_id', $1, true)`, p.OrgID.String()); err != nil {
			t.Fatalf("set org: %v", err)
		}
		var n int
		if err := tx.QueryRowContext(ctx,
			`SELECT count(*) FROM ibex_core.idempotency_ledger WHERE dedupe_key='shared-key'`,
		).Scan(&n); err != nil {
			t.Fatalf("count: %v", err)
		}
		return n
	}
	if got := countForOrg(orgA); got != 1 {
		t.Fatalf("org A row count = %d, want 1", got)
	}
	if got := countForOrg(orgB); got != 1 {
		t.Fatalf("org B row count = %d, want 1", got)
	}
}
