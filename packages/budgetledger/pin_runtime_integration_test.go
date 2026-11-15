//go:build integration

package budgetledger_test

import (
	"context"
	"database/sql"
	"testing"
	"time"

	migratepg "github.com/Rick1330/ibex-harness/infra/migrations/postgres"
	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/budgetledger"
	"github.com/google/uuid"
)

// TestPostgresLedger_Claim_AsRuntimePinsTenantRole is the positive control for
// the pin on the admission path. ibex_runtime holds no table grant, so Claim can
// read ibex_billing.budget_periods and write ibex_core.budget_reservations only
// because withOrgTx assumes ibex_app first; before the pin it is 42501.
//
// Two orgs claiming the same reservation key must each own a distinct hold. A
// shared hold would mean org B resolved org A's row, which is the cross-tenant
// failure the pin exists to prevent.
func TestPostgresLedger_Claim_AsRuntimePinsTenantRole(t *testing.T) {
	dsn := runtimeconn.DSN()
	if err := migratepg.Up(dsn); err != nil {
		t.Fatalf("migrate up: %v", err)
	}

	owner := runtimeconn.OpenDB(t, dsn)
	defer func() { _ = owner.Close() }()

	orgA := seedLedgerPrincipal(t, owner, "pin-budget-a")
	orgB := seedLedgerPrincipal(t, owner, "pin-budget-b")
	seedHardCapPeriod(t, owner, orgA.OrgID)
	seedHardCapPeriod(t, owner, orgB.OrgID)

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	ledger, err := budgetledger.NewPostgresLedger(runtimeDB, time.Minute)
	if err != nil {
		t.Fatalf("NewPostgresLedger: %v", err)
	}

	const key = "pin-shared-key"
	hashA := budgetledger.HashRequest([]byte("tenant-a"))
	hashB := budgetledger.HashRequest([]byte("tenant-b"))
	heldA := claimAsRuntime(t, ledger, runtimeClaim{principal: orgA, key: key, hash: hashA})
	heldB := claimAsRuntime(t, ledger, runtimeClaim{principal: orgB, key: key, hash: hashB})
	if heldA.Kind != budgetledger.ClaimOwned || heldB.Kind != budgetledger.ClaimOwned {
		t.Fatalf("kinds=%s/%s want owned/owned", heldA.Kind, heldB.Kind)
	}
	if heldA.Reservation.ID == heldB.Reservation.ID {
		t.Fatalf("org B owns org A's reservation %s", heldA.Reservation.ID)
	}

	// Org A's own key still resolves to org A's live hold. ClaimInProgress
	// carries a retry hint, not the reservation, so the kind is the assertion.
	againA := claimAsRuntime(t, ledger, runtimeClaim{principal: orgA, key: key, hash: hashA})
	if againA.Kind != budgetledger.ClaimInProgress {
		t.Fatalf("org A re-claim kind=%s want in_progress", againA.Kind)
	}
}

// runtimeClaim is one claim attempt over the runtime login: the tenant that
// claims, and the dedupe key and body hash it claims under.
type runtimeClaim struct {
	principal budgetledger.Principal
	key       string
	hash      string
}

// claimAsRuntime issues the claim over the ibex_runtime connection and fails the
// test if the pin let a permission denial through.
func claimAsRuntime(t *testing.T, ledger *budgetledger.PostgresLedger, c runtimeClaim) budgetledger.ClaimOutcome {
	t.Helper()
	out, err := ledger.Claim(context.Background(), c.principal, budgetledger.ClaimRequest{
		Key: c.key, RequestHash: c.hash, EstimatedCents: 10,
	})
	runtimeconn.RequireNoPermissionDenied(t, err, "Claim")
	if err != nil {
		t.Fatalf("Claim as ibex_runtime: %v", err)
	}
	return out
}

func seedLedgerPrincipal(t *testing.T, db *sql.DB, label string) budgetledger.Principal {
	t.Helper()
	ctx := context.Background()
	suffix := uuid.NewString()
	var orgID, agentID string
	err := runtimeconn.WithOwnerTx(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		if err := tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.organizations (name, slug) VALUES ($1, $2) RETURNING id::text`,
			label, label+"-"+suffix[:8]).Scan(&orgID); err != nil {
			return err
		}
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		return tx.QueryRowContext(ctx,
			`INSERT INTO ibex_core.agents (org_id, name, slug) VALUES ($1::uuid, $2, $3) RETURNING id::text`,
			orgID, label+"-agent", label+"-agent-"+suffix[:8]).Scan(&agentID)
	})
	if err != nil {
		t.Fatalf("seed principal: %v", err)
	}
	return budgetledger.Principal{OrgID: uuid.MustParse(orgID), AgentID: uuid.MustParse(agentID)}
}

func seedHardCapPeriod(t *testing.T, db *sql.DB, orgID uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	now := time.Now().UTC()
	err := runtimeconn.WithOwnerTx(ctx, db, func(tx *sql.Tx) error {
		// nosemgrep: go_sql_rule-concat-sqli -- static test fixture SQL; every value is a bound parameter.
		_, err := tx.ExecContext(ctx, `
			INSERT INTO ibex_billing.budget_periods
				(org_id, period_start, period_end, cap_cents, spent_cents_cached, enforcement_mode)
			VALUES ($1::uuid, $2, $3, 100000, 0, 'hard_cap')`, orgID, now.Add(-time.Hour), now.Add(time.Hour))
		return err
	})
	if err != nil {
		t.Fatalf("seed hard-cap period: %v", err)
	}
}
