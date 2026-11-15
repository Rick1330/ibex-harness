//go:build integration

package evidenceoutbox_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/infra/testing/pgprovision"
	"github.com/Rick1330/ibex-harness/infra/testing/runtimeconn"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

// TestStore_PersistRun_AsRuntimePinsTenantRole is the positive control for the
// pin on the evidence write path. ibex_runtime holds no table grant, so
// PersistRun reaches ibex_core.evidence_runs and ibex_core.evidence_outbox only
// because persistRunTx assumes ibex_app first; before the pin it is 42501.
//
// The tenant assertion is a shared request id: findExistingRun is keyed on
// (org_id, request_id), so if the scope were dropped org B would replay org A's
// run instead of committing its own.
func TestStore_PersistRun_AsRuntimePinsTenantRole(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	orgA := seedOrg(t, db)
	orgB := seedOrg(t, db)

	pgprovision.CapabilityLogins(t, integrationDSN())
	runtimeDB := runtimeconn.OpenRuntimeDB(t, integrationDSN())
	defer func() { _ = runtimeDB.Close() }()
	store := mustStore(t, runtimeDB)

	const requestID = "pin-shared-request-id"
	firstA := persistPinnedRun(t, store, orgA, requestID)
	if firstA.Replayed {
		t.Fatalf("first persist of org A reported a replay of run %s", firstA.RunID)
	}

	firstB := persistPinnedRun(t, store, orgB, requestID)
	if firstB.Replayed {
		t.Fatalf("org B replayed org A's run %s instead of committing its own", firstA.RunID)
	}
	if firstA.RunID == firstB.RunID {
		t.Fatalf("org A and org B share run %s", firstA.RunID)
	}

	// Org A's own request id still resolves to org A's run.
	againA := persistPinnedRun(t, store, orgA, requestID)
	if !againA.Replayed || againA.RunID != firstA.RunID {
		t.Fatalf("org A re-persist replayed=%v run=%s want true/%s", againA.Replayed, againA.RunID, firstA.RunID)
	}
}

func persistPinnedRun(t *testing.T, store *evidenceoutbox.Store, orgID uuid.UUID, requestID string) evidenceoutbox.PersistResult {
	t.Helper()
	result, err := store.PersistRun(context.Background(), evidenceoutbox.RunInput{
		OrgID:          orgID,
		RequestID:      requestID,
		TraceID:        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		RedactionClass: evidenceoutbox.RedactionClassMetadata,
		Producer: &evidenceoutbox.ProducerMetadata{
			RedactionClass: evidenceoutbox.RedactionClassMetadata, RedactionProofVersion: "redaction/v1",
			ResourceType: "evidence_run", ResourceID: requestID, ResourceVersion: 1,
			Source: "pin-integration-test",
		},
		TombstoneFence: &evidenceoutbox.TombstoneFence{
			ResourceType: "evidence_run", ResourceID: requestID, ResourceVersion: 1,
		},
		Spans:   []evidenceoutbox.SpanInput{{SpanID: "1111111111111111", OperationKind: "proxy.chat"}},
		Metrics: &evidenceoutbox.AssemblyMetrics{TotalMs: 1},
	})
	runtimeconn.RequireNoPermissionDenied(t, err, "PersistRun")
	if err != nil {
		t.Fatalf("PersistRun as ibex_runtime: %v", err)
	}
	return result
}
