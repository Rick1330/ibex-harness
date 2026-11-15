//go:build integration

package idempotency

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
)

// TestPostgresLedger_Claim_AsRuntimePinsTenantRole is the positive control for
// the pin on both ledger transactions. ibex_runtime holds no table grant, so
// Claim and withClaimTx reach ibex_core.idempotency_ledger only because the
// transaction assumes ibex_app first; before the pin the claim is 42501.
//
// Two orgs claiming the same dedupe key must each own a distinct row. A shared
// row would let org B replay org A's response, which is the cross-tenant leak
// the pin exists to prevent.
func TestPostgresLedger_Claim_AsRuntimePinsTenantRole(t *testing.T) {
	db := openLedgerDB(t)
	dsn := ledgerDSN()
	pA, pB := seedPrincipal(t, db)

	pgprovision.CapabilityLogins(t, dsn)
	runtimeDB := runtimeconn.OpenRuntimeDB(t, dsn)
	defer func() { _ = runtimeDB.Close() }()

	ledger, err := NewPostgresLedger(runtimeDB, time.Minute)
	if err != nil {
		t.Fatalf("NewPostgresLedger: %v", err)
	}

	const key = "pin-shared-dedupe-key"
	hashA := HashRequest([]byte("tenant-a"))
	hashB := HashRequest([]byte("tenant-b"))

	heldA := claimLedgerAsRuntime(t, ledger, runtimeClaim{principal: pA, key: key, hash: hashA})
	heldB := claimLedgerAsRuntime(t, ledger, runtimeClaim{principal: pB, key: key, hash: hashB})
	if heldA.Kind != ClaimOwned || heldB.Kind != ClaimOwned {
		t.Fatalf("kinds=%s/%s want owned/owned", heldA.Kind, heldB.Kind)
	}
	if heldA.Claim.ID == heldB.Claim.ID {
		t.Fatalf("org B owns org A's ledger row %s", heldA.Claim.ID)
	}

	// Org A's own key still resolves to org A's in-flight claim.
	againA := claimLedgerAsRuntime(t, ledger, runtimeClaim{principal: pA, key: key, hash: hashA})
	if againA.Kind != ClaimInProgress || againA.Claim.ID != heldA.Claim.ID {
		t.Fatalf("org A re-claim kind=%s id=%s want in_progress/%s", againA.Kind, againA.Claim.ID, heldA.Claim.ID)
	}
}

// runtimeClaim is one claim attempt over the runtime login: the tenant that
// claims, and the dedupe key and body hash it claims under.
type runtimeClaim struct {
	principal Principal
	key       string
	hash      string
}

// claimLedgerAsRuntime issues the claim over the ibex_runtime connection and
// fails the test if the pin let a permission denial through.
func claimLedgerAsRuntime(t *testing.T, ledger *PostgresLedger, c runtimeClaim) ClaimOutcome {
	t.Helper()
	out, err := ledger.Claim(context.Background(), c.principal, c.key, c.hash)
	runtimeconn.RequireNoPermissionDenied(t, err, "Claim")
	if err != nil {
		t.Fatalf("Claim as ibex_runtime: %v", err)
	}
	return out
}
