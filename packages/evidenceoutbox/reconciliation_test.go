package evidenceoutbox

import (
	"database/sql"
	"testing"

	"github.com/google/uuid"
)

func TestReconciliationHelpers_ValidateAndClassifyRows(t *testing.T) {
	agentID, sessionID := uuid.New(), uuid.New()
	in := RunInput{OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID, RequestID: "req", TraceID: "trace"}
	for name, candidate := range map[string]RunInput{
		"missing org":     {AgentID: &agentID, SessionID: &sessionID, RequestID: "req", TraceID: "trace"},
		"missing agent":   {OrgID: in.OrgID, SessionID: &sessionID, RequestID: "req", TraceID: "trace"},
		"missing session": {OrgID: in.OrgID, AgentID: &agentID, RequestID: "req", TraceID: "trace"},
		"missing request": {OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, TraceID: "trace"},
	} {
		if validReconciliationInput(candidate) {
			t.Errorf("%s: invalid input accepted", name)
		}
	}
	if !validReconciliationInput(in) {
		t.Fatal("valid reconciliation input rejected")
	}
	classifyOutboxRows(t, in)
}

func classifyOutboxRows(t *testing.T, in RunInput) {
	rowID := uuid.New()
	rows := []struct {
		name, status string
		wantRetry    bool
		wantErr      bool
	}{
		{name: "pending", status: "pending", wantRetry: true},
		{name: "failed", status: "failed", wantRetry: true},
		{name: "in flight", status: "in_flight", wantRetry: true},
		{name: "delivered", status: "delivered"},
		{name: "poison", status: "poison", wantErr: true},
		{name: "unknown", status: "other", wantErr: true},
	}
	for _, tc := range rows {
		t.Run(tc.name, func(t *testing.T) {
			proof := ReconciliationProof{}
			row := OutboxRow{
				ID: rowID, OrgID: in.OrgID, EventID: uuid.New(), AggregateID: in.RequestID, AggregateSeq: 1,
				SchemaVersion: SchemaVersion, EventType: EventTypeRunCommitted, Payload: validRelayPayload(),
				PayloadDigestScheme: PayloadDigestSchemeJCSV1, PayloadDigest: validPayloadDigest(validRelayPayload()), DeliveryStatus: tc.status,
			}
			err := addVerifiedOutboxRow(in, &proof, row)
			if (err != nil) != tc.wantErr {
				t.Fatalf("error=%v wantErr=%v", err, tc.wantErr)
			}
			if !tc.wantErr {
				if len(proof.OutboxIDs) != 1 || (len(proof.RetryableOutboxIDs) == 1) != tc.wantRetry {
					t.Fatalf("proof=%+v wantRetry=%v", proof, tc.wantRetry)
				}
			}
		})
	}
}

func TestReconciliationHelpers_ParseOptionalUUID(t *testing.T) {
	if got, err := parseOptionalUUID(sql.NullString{}); err != nil || got != nil {
		t.Fatalf("invalid null UUID result=%v err=%v", got, err)
	}
	if got, err := parseOptionalUUID(sql.NullString{Valid: true}); err != nil || got != nil {
		t.Fatalf("empty UUID result=%v err=%v", got, err)
	}
	want := uuid.New()
	got, err := parseOptionalUUID(sql.NullString{Valid: true, String: want.String()})
	if err != nil || got == nil || *got != want {
		t.Fatalf("valid UUID result=%v err=%v", got, err)
	}
	if _, err := parseOptionalUUID(sql.NullString{Valid: true, String: "not-a-uuid"}); err == nil {
		t.Fatal("malformed UUID accepted")
	}
	clone := cloneUUIDPointer(&want)
	if clone == nil || *clone != want || clone == &want {
		t.Fatalf("UUID was not cloned: %v", clone)
	}
}

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

func TestReconciliationProof_RejectsInvalidOutboxSetsAndNilIdentity(t *testing.T) {
	agentID, sessionID := uuid.New(), uuid.New()
	in := RunInput{OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID, RequestID: "req", TraceID: "trace"}
	rowID, otherID := uuid.New(), uuid.New()
	base := ReconciliationProof{OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, RequestID: in.RequestID, TraceID: in.TraceID, RunID: uuid.New(), OutboxIDs: []uuid.UUID{rowID}}
	duplicate := base
	duplicate.OutboxIDs = []uuid.UUID{rowID, rowID}
	if duplicate.Matches(in) {
		t.Fatal("duplicate outbox proof accepted")
	}
	foreignRetry := base
	foreignRetry.RetryableOutboxIDs = []uuid.UUID{otherID}
	if foreignRetry.Matches(in) {
		t.Fatal("foreign retry proof accepted")
	}
	if (ReconciliationProof{OrgID: in.OrgID, RequestID: in.RequestID, TraceID: in.TraceID, RunID: uuid.New(), OutboxIDs: []uuid.UUID{rowID}}).Matches(in) {
		t.Fatal("proof with missing scoped identities accepted")
	}
	nonNil := uuid.New()
	if !sameUUIDPtr(nil, &uuid.Nil) || sameUUIDPtr(nil, &nonNil) || !sameUUIDPtr(nil, nil) {
		t.Fatal("nil UUID pointer comparison mismatch")
	}
}
