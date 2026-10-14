package evidenceoutbox

import (
	"testing"

	"github.com/google/uuid"
)

func TestReconciliationProof_MatchesRequestAndRetryableSubset(t *testing.T) {
	agentID, sessionID := uuid.New(), uuid.New()
	in := RunInput{OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID, RequestID: "req-1", TraceID: "aabbccddeeff00112233445566778899"}
	rowID := uuid.New()
	proof := ReconciliationProof{
		OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, RequestID: in.RequestID,
		TraceID: in.TraceID, RunID: uuid.New(), OutboxIDs: []uuid.UUID{rowID},
		RetryableOutboxIDs: []uuid.UUID{rowID},
	}
	if !proof.Matches(in) || !proof.HasDurableRetry(in) || proof.AllDelivered(in) {
		t.Fatalf("valid retry proof rejected: %+v", proof)
	}

	wrong := in
	wrong.RequestID = "another-request"
	if proof.Matches(wrong) || proof.HasDurableRetry(wrong) {
		t.Fatal("proof matched a different request")
	}

	proof.RetryableOutboxIDs = []uuid.UUID{uuid.New()}
	if proof.Matches(in) {
		t.Fatal("proof accepted retry row not present in outbox ID set")
	}
}

func TestReconciliationProof_AllDeliveredRequiresMatchingRun(t *testing.T) {
	agentID, sessionID := uuid.New(), uuid.New()
	in := RunInput{OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID, RequestID: "req-2", TraceID: "11223344556677889900aabbccddeeff"}
	proof := ReconciliationProof{
		OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, RequestID: in.RequestID,
		TraceID: in.TraceID, RunID: uuid.New(), OutboxIDs: []uuid.UUID{uuid.New()},
	}
	if !proof.AllDelivered(in) {
		t.Fatalf("all-delivered proof rejected: %+v", proof)
	}
	proof.OutboxIDs = nil
	if proof.AllDelivered(in) {
		t.Fatal("empty outbox proof treated as durable replay")
	}
}
