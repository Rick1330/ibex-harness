package evidenceoutbox

import (
	"context"
	"database/sql"
	"errors"
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

func TestReconcileRun_RejectsInvalidInputBeforeSQL(t *testing.T) {
	store := &Store{}
	if _, err := store.ReconcileRun(context.Background(), RunInput{}); err != ErrReconciliationNotProven {
		t.Fatalf("error=%v want %v", err, ErrReconciliationNotProven)
	}
}

func TestReconcileRun_SQLFailurePaths(t *testing.T) {
	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	in := RunInput{OrgID: orgID, AgentID: &agentID, SessionID: &sessionID, RequestID: "req", TraceID: "aabbccddeeff00112233445566778899"}
	tests := []struct {
		name  string
		setup func(sqlmock.Sqlmock, RunInput)
	}{
		{name: "begin", setup: func(m sqlmock.Sqlmock, _ RunInput) { m.ExpectBegin().WillReturnError(sql.ErrConnDone) }},
		{name: "rls", setup: func(m sqlmock.Sqlmock, in RunInput) {
			m.ExpectBegin()
			m.ExpectExec(`SELECT set_config`).WithArgs(in.OrgID.String()).WillReturnError(sql.ErrConnDone)
			m.ExpectRollback()
		}},
		{name: "run missing", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcilePrefix(m, in)
			m.ExpectQuery(`SELECT id, agent_id::text`).WithArgs(in.OrgID, in.RequestID).WillReturnError(sql.ErrNoRows)
			m.ExpectRollback()
		}},
		{name: "run malformed agent", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcilePrefix(m, in)
			m.ExpectQuery(`SELECT id, agent_id::text`).WithArgs(in.OrgID, in.RequestID).WillReturnRows(sqlmock.NewRows([]string{"id", "agent_id", "session_id", "trace_id"}).AddRow(uuid.New(), "bad", sessionID.String(), in.TraceID))
			m.ExpectRollback()
		}},
		{name: "run malformed session", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcilePrefix(m, in)
			m.ExpectQuery(`SELECT id, agent_id::text`).WithArgs(in.OrgID, in.RequestID).WillReturnRows(sqlmock.NewRows([]string{"id", "agent_id", "session_id", "trace_id"}).AddRow(uuid.New(), agentID.String(), "bad", in.TraceID))
			m.ExpectRollback()
		}},
		{name: "run mismatch", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcilePrefix(m, in)
			m.ExpectQuery(`SELECT id, agent_id::text`).WithArgs(in.OrgID, in.RequestID).WillReturnRows(sqlmock.NewRows([]string{"id", "agent_id", "session_id", "trace_id"}).AddRow(uuid.New(), agentID.String(), sessionID.String(), "wrong-trace"))
			m.ExpectRollback()
		}},
		{name: "outbox query", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcileRun(m, in, agentID, sessionID)
			m.ExpectQuery(`SELECT id, org_id, event_id, aggregate_id`).WithArgs(in.OrgID, in.RequestID).WillReturnError(sql.ErrConnDone)
			m.ExpectRollback()
		}},
		{name: "outbox scan", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcileRun(m, in, agentID, sessionID)
			m.ExpectQuery(`SELECT id, org_id, event_id, aggregate_id`).WithArgs(in.OrgID, in.RequestID).WillReturnRows(sqlmock.NewRows([]string{"id"}).AddRow(uuid.New()))
			m.ExpectRollback()
		}},
		{name: "commit", setup: func(m sqlmock.Sqlmock, in RunInput) {
			expectReconcileRun(m, in, agentID, sessionID)
			payload := validRelayPayload()
			m.ExpectQuery(`SELECT id, org_id, event_id, aggregate_id`).WithArgs(in.OrgID, in.RequestID).WillReturnRows(sqlmock.NewRows([]string{"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version", "event_type", "payload", "payload_digest", "payload_digest_scheme", "delivery_status"}).AddRow(uuid.New(), in.OrgID, uuid.New(), in.RequestID, 1, SchemaVersion, EventTypeRunCommitted, payload, validPayloadDigest(payload), PayloadDigestSchemeJCSV1, "delivered"))
			m.ExpectCommit().WillReturnError(sql.ErrConnDone)
		}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			defer func() { _ = db.Close() }()
			store := &Store{db: db}
			tc.setup(mock, in)
			if _, err := store.ReconcileRun(context.Background(), in); err == nil {
				t.Fatal("expected reconciliation error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func expectReconcilePrefix(m sqlmock.Sqlmock, in RunInput) {
	m.ExpectBegin()
	m.ExpectExec(`SELECT set_config`).WithArgs(in.OrgID.String()).WillReturnResult(sqlmock.NewResult(0, 1))
}

func expectReconcileRun(m sqlmock.Sqlmock, in RunInput, agentID, sessionID uuid.UUID) {
	expectReconcilePrefix(m, in)
	m.ExpectQuery(`SELECT id, agent_id::text`).WithArgs(in.OrgID, in.RequestID).
		WillReturnRows(sqlmock.NewRows([]string{"id", "agent_id", "session_id", "trace_id"}).AddRow(uuid.New(), agentID.String(), sessionID.String(), in.TraceID))
}

func TestReconcileRun_EmptyAndMalformedOutboxProofsFailClosed(t *testing.T) {
	orgID, agentID, sessionID := uuid.New(), uuid.New(), uuid.New()
	in := RunInput{OrgID: orgID, AgentID: &agentID, SessionID: &sessionID, RequestID: "req", TraceID: "aabbccddeeff00112233445566778899"}
	tests := []struct {
		name string
		rows *sqlmock.Rows
	}{
		{name: "empty outbox", rows: sqlmock.NewRows([]string{"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version", "event_type", "payload", "payload_digest", "payload_digest_scheme", "delivery_status"})},
		{name: "invalid row", rows: sqlmock.NewRows([]string{"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version", "event_type", "payload", "payload_digest", "payload_digest_scheme", "delivery_status"}).AddRow(uuid.New(), uuid.New(), uuid.New(), in.RequestID, 1, SchemaVersion, EventTypeRunCommitted, validRelayPayload(), validPayloadDigest(validRelayPayload()), PayloadDigestSchemeJCSV1, "delivered")},
		{name: "row iteration error", rows: sqlmock.NewRows([]string{"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version", "event_type", "payload", "payload_digest", "payload_digest_scheme", "delivery_status"}).RowError(0, errors.New("row failed"))},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			defer func() { _ = db.Close() }()
			store := &Store{db: db}
			expectReconcileRun(mock, in, agentID, sessionID)
			mock.ExpectQuery(`SELECT id, org_id, event_id, aggregate_id`).WithArgs(in.OrgID, in.RequestID).WillReturnRows(tc.rows)
			mock.ExpectRollback()
			if _, err := store.ReconcileRun(context.Background(), in); err == nil {
				t.Fatal("expected proof failure")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestReconciliationHelpers_RejectInvalidRetryAndRows(t *testing.T) {
	agentID, sessionID := uuid.New(), uuid.New()
	in := RunInput{OrgID: uuid.New(), AgentID: &agentID, SessionID: &sessionID, RequestID: "req", TraceID: "trace"}
	proof := ReconciliationProof{OrgID: in.OrgID, AgentID: &agentID, SessionID: &sessionID, RequestID: in.RequestID, TraceID: in.TraceID, RunID: uuid.New(), OutboxIDs: []uuid.UUID{uuid.New()}}
	proof.RetryableOutboxIDs = []uuid.UUID{uuid.Nil}
	if proof.Matches(in) {
		t.Fatal("nil retry ID accepted")
	}
	if cloneUUIDPointer(nil) != nil {
		t.Fatal("nil UUID clone should remain nil")
	}
	if err := addVerifiedOutboxRow(in, &proof, OutboxRow{}); err != ErrReconciliationNotProven {
		t.Fatalf("invalid row error=%v", err)
	}
}
