//go:build integration

package evidenceoutbox_test

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

func TestIntegration_ReconcileRun_ProvesRetryableThenDeliveredState(t *testing.T) {
	db := openTestDB(t)
	defer func() { _ = db.Close() }()
	orgID := seedOrg(t, db)
	sessionID := seedSession(t, db, orgID)
	store := mustStore(t, db)
	in := certifiedPersistRunInput(orgID, sessionID)
	result, err := store.PersistRun(context.Background(), in)
	if err != nil {
		t.Fatalf("PersistRun: %v", err)
	}

	proof, err := store.ReconcileRun(context.Background(), in)
	if err != nil {
		t.Fatalf("ReconcileRun pending: %v", err)
	}
	if !proof.HasDurableRetry(in) || proof.RunID != result.RunID {
		t.Fatalf("pending rows did not prove retryability: %+v", proof)
	}

	tx := beginServiceTx(t, db)
	if _, err := tx.ExecContext(context.Background(), `
UPDATE ibex_core.evidence_outbox
SET delivery_status = 'delivered', delivered_at = NOW()
WHERE org_id = $1 AND aggregate_id = $2`, orgID, in.RequestID); err != nil {
		t.Fatalf("mark rows delivered: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("commit delivered state: %v", err)
	}

	delivered, err := store.ReconcileRun(context.Background(), in)
	if err != nil {
		t.Fatalf("ReconcileRun delivered: %v", err)
	}
	if !delivered.AllDelivered(in) || delivered.HasDurableRetry(in) {
		t.Fatalf("delivered rows did not prove replay-safe completion: %+v", delivered)
	}

	wrong := in
	wrong.TraceID = "00112233445566778899aabbccddeeff"
	if _, err := store.ReconcileRun(context.Background(), wrong); err == nil {
		t.Fatal("reconciliation accepted a different trace identity")
	}
}

func certifiedPersistRunInput(orgID, sessionID uuid.UUID) evidenceoutbox.RunInput {
	in := fullPersistRunInput(orgID, sessionID)
	in.Tools = nil
	in.SessionEvents = nil
	in.Directive = &evidenceoutbox.DirectiveSnapshot{ContentHash: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
	in.CaptureMode = "metadata"
	in.SampleDecision = "included"
	in.RedactionClass = evidenceoutbox.RedactionClassMetadata
	in.TombstoneFence = &evidenceoutbox.TombstoneFence{ResourceType: "session", ResourceID: sessionID.String(), ResourceVersion: 1}
	in.Producer = &evidenceoutbox.ProducerMetadata{
		RedactionClass: evidenceoutbox.RedactionClassMetadata, RedactionProofVersion: "session-metadata-allowlist/v1",
		ResourceType: "session", ResourceID: sessionID.String(), ResourceVersion: 1, Source: "test.session.evidence",
	}
	return in
}
