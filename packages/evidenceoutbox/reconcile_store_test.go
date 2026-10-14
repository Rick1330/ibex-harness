package evidenceoutbox

import (
	"context"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func TestReconcileRun_VerifiesDurableOutboxProof(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	orgID, agentID, sessionID, runID, outboxID := uuid.New(), uuid.New(), uuid.New(), uuid.New(), uuid.New()
	in := RunInput{OrgID: orgID, AgentID: &agentID, SessionID: &sessionID, RequestID: "req-reconcile", TraceID: "aabbccddeeff00112233445566778899"}
	payload := validRelayPayload()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(orgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(`SELECT id, agent_id::text, session_id::text, trace_id`).WithArgs(orgID, in.RequestID).
		WillReturnRows(sqlmock.NewRows([]string{"id", "agent_id", "session_id", "trace_id"}).
			AddRow(runID, agentID.String(), sessionID.String(), in.TraceID))
	mock.ExpectQuery(`SELECT id, org_id, event_id, aggregate_id`).WithArgs(orgID, in.RequestID).
		WillReturnRows(sqlmock.NewRows([]string{"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version", "event_type", "payload", "payload_digest", "payload_digest_scheme", "delivery_status"}).
			AddRow(outboxID, orgID, uuid.New(), in.RequestID, 1, SchemaVersion, EventTypeRunCommitted, payload, validPayloadDigest(payload), PayloadDigestSchemeJCSV1, "delivered"))
	mock.ExpectCommit()

	proof, err := store.ReconcileRun(context.Background(), in)
	if err != nil {
		t.Fatalf("ReconcileRun: %v", err)
	}
	if !proof.Matches(in) || !proof.AllDelivered(in) || len(proof.OutboxIDs) != 1 || proof.OutboxIDs[0] != outboxID {
		t.Fatalf("proof=%+v", proof)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
