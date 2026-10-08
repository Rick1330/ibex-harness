package evidenceoutbox

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

func TestUnit_NewStore_RequiresDB(t *testing.T) {
	t.Parallel()
	if _, err := NewStore(nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_PersistRun_Validation(t *testing.T) {
	t.Parallel()
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.PersistRun(context.Background(), RunInput{})
	if err == nil {
		t.Fatal("expected validation error")
	}
}

func marshalOutboxPayloadForTest(
	t *testing.T,
	payload any,
	class RedactionClass,
	fence *TombstoneFence,
) map[string]json.RawMessage {
	t.Helper()
	raw, err := marshalOutboxPayload(payload, class, fence)
	if err != nil {
		t.Fatalf("marshalOutboxPayload: %v", err)
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatalf("unmarshal outbox payload: %v", err)
	}
	return fields
}

func TestUnit_MarshalOutboxPayloadAddsTrustedMetadata(t *testing.T) {
	t.Parallel()
	fence := &TombstoneFence{ResourceType: "evidence_run", ResourceID: "run-1", ResourceVersion: 7}
	payload := marshalOutboxPayloadForTest(t, map[string]any{"event_id": "evt-1"}, RedactionClassMetadata, fence)
	if string(payload["redaction_class"]) != `"metadata"` {
		t.Fatalf("redaction_class=%s", payload["redaction_class"])
	}
	var gotFence TombstoneFence
	if err := json.Unmarshal(payload["tombstone_fence"], &gotFence); err != nil {
		t.Fatal(err)
	}
	if gotFence != *fence {
		t.Fatalf("tombstone_fence=%+v want %+v", gotFence, *fence)
	}
}

func TestUnit_MarshalOutboxPayloadDefaultsUnclassified(t *testing.T) {
	t.Parallel()
	payload := marshalOutboxPayloadForTest(t, map[string]any{"event_id": "evt-2"}, "", nil)
	if string(payload["redaction_class"]) != `"unclassified"` {
		t.Fatalf("missing producer classification was upgraded: %s", payload["redaction_class"])
	}
}

func TestUnit_MarshalOutboxPayloadAcceptsProhibitedClass(t *testing.T) {
	t.Parallel()
	payload := marshalOutboxPayloadForTest(
		t, map[string]any{"event_id": "evt-3"}, RedactionClassProhibited, nil,
	)
	if string(payload["redaction_class"]) != `"prohibited"` {
		t.Fatalf("redaction_class=%s want prohibited", payload["redaction_class"])
	}
}

func TestUnit_MarshalOutboxPayloadRejectsUnsupportedClass(t *testing.T) {
	t.Parallel()
	if _, err := marshalOutboxPayload(map[string]any{"event_id": "evt-4"}, RedactionClass("unknown"), nil); err == nil {
		t.Fatal("expected unsupported redaction class to be rejected")
	}
}

func TestUnit_MarshalOutboxPayloadRejectsCallerSuppliedClass(t *testing.T) {
	t.Parallel()
	if _, err := marshalOutboxPayload(
		map[string]any{"redaction_class": "metadata"}, RedactionClassMetadata, nil,
	); err == nil {
		t.Fatal("expected caller-supplied redaction_class to be rejected")
	}
}

func TestUnit_MarshalOutboxPayloadRejectsCallerSuppliedFence(t *testing.T) {
	t.Parallel()
	if _, err := marshalOutboxPayload(
		map[string]any{"tombstone_fence": map[string]any{}}, RedactionClassMetadata, nil,
	); err == nil {
		t.Fatal("expected caller-supplied tombstone_fence to be rejected")
	}
}

func TestUnit_MarshalOutboxPayloadRejectsUnserializablePayload(t *testing.T) {
	t.Parallel()
	_, err := marshalOutboxPayload(make(chan int), RedactionClassMetadata, nil)
	var unsupported *json.UnsupportedTypeError
	if !errors.As(err, &unsupported) {
		t.Fatalf("err=%v want unsupported-type marshal error", err)
	}
}

func TestUnit_DecodePayloadFieldsRejectsMalformedJSON(t *testing.T) {
	t.Parallel()
	if _, err := decodePayloadFields([]byte("{")); err == nil {
		t.Fatal("expected malformed JSON to be rejected")
	}
}

func TestUnit_MarshalOutboxPayloadRequiresJSONObject(t *testing.T) {
	t.Parallel()
	_, err := marshalOutboxPayload(nil, RedactionClassMetadata, nil)
	if err == nil || !strings.Contains(err.Error(), "payload must be a JSON object") {
		t.Fatalf("err=%v want JSON object validation error", err)
	}
}

func TestUnit_MarshalOutboxPayloadRejectsInvalidFence(t *testing.T) {
	t.Parallel()
	_, err := marshalOutboxPayload(
		map[string]any{"event_id": "evt-5"}, RedactionClassMetadata, &TombstoneFence{},
	)
	if !errors.Is(err, errTombstoneFenceInvalid) {
		t.Fatalf("err=%v want invalid tombstone fence", err)
	}
}

func TestUnit_ValidateRunInputRejectsInvalidFence(t *testing.T) {
	t.Parallel()
	err := validateRunInput(RunInput{
		TombstoneFence: &TombstoneFence{ResourceType: "memory", ResourceID: "mem-1"},
	})
	if !errors.Is(err, errTombstoneFenceInvalid) {
		t.Fatalf("err=%v want invalid tombstone fence", err)
	}
}

func TestUnit_PersistRun_HappyPathMinimal(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}

	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	digest := "sha256:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_runs`).
		WithArgs(
			sqlmock.AnyArg(), org, sqlmock.AnyArg(), sqlmock.AnyArg(), "req-1",
			"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", sqlmock.AnyArg(), sqlmock.AnyArg(),
			sqlmock.AnyArg(), sqlmock.AnyArg(), sqlmock.AnyArg(), sqlmock.AnyArg(),
			sqlmock.AnyArg(), sqlmock.AnyArg(), sqlmock.AnyArg(), sqlmock.AnyArg(),
			digest,
		).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	res, err := store.PersistRun(context.Background(), RunInput{
		OrgID:             org,
		RequestID:         "req-1",
		TraceID:           "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		DeployImageDigest: "  " + digest + "  ",
	})
	if err != nil {
		t.Fatalf("PersistRun: %v", err)
	}
	if res.RunID == uuid.Nil {
		t.Fatal("empty run id")
	}
	if res.AggregateID != "req-1" {
		t.Fatalf("aggregate=%q want request_id", res.AggregateID)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_PersistRun_WithChildren(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	store, err := NewStore(db)
	if err != nil {
		t.Fatal(err)
	}

	org := uuid.New()
	mem := uuid.New()
	rank := 1
	sim := 0.9
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_runs`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_spans`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_assembly_metrics`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_score_candidates`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_directive_snapshots`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_tool_audits`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.session_events`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	sessionID := uuid.New()
	_, err = store.PersistRun(context.Background(), RunInput{
		OrgID: org, RequestID: "req-2", TraceID: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		RootSpanID: "1111111111111111", MetricsSpanID: "2222222222222222",
		Spans:   []SpanInput{{SpanID: "1111111111111111", OperationKind: "proxy.chat"}},
		Metrics: &AssemblyMetrics{TotalMs: 5},
		Candidates: []ScoreCandidate{
			{MemoryID: mem, RetrievalRank: 1, FinalRank: &rank, Similarity: &sim, Exclusion: "included"},
		},
		Directive: &DirectiveSnapshot{ContentHash: "h"},
		Tools:     []ToolAudit{{ToolName: "search"}},
		SessionEvents: []SessionEventInput{
			{SessionID: sessionID, SequenceNumber: 1, EventType: "evidence_assembly"},
		},
	})
	if err != nil {
		t.Fatalf("PersistRun: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_PersistRun_TxnSetupFails(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name  string
		setup func(sqlmock.Sqlmock)
	}{
		{
			name: "begin",
			setup: func(mock sqlmock.Sqlmock) {
				mock.ExpectBegin().WillReturnError(context.DeadlineExceeded)
			},
		},
		{
			name: "rls",
			setup: func(mock sqlmock.Sqlmock) {
				mock.ExpectBegin()
				mock.ExpectExec(`SELECT set_config`).WillReturnError(context.Canceled)
				mock.ExpectRollback()
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			defer func() { _ = db.Close() }()
			store, err := NewStore(db)
			if err != nil {
				t.Fatal(err)
			}
			tc.setup(mock)
			_, err = store.PersistRun(context.Background(), RunInput{
				OrgID: uuid.New(), RequestID: "r", TraceID: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			})
			if err == nil {
				t.Fatal("expected txn setup error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestUnit_DeployImageDigestOrNull(t *testing.T) {
	t.Parallel()
	valid := "sha256:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
	cases := []struct {
		name string
		in   string
		want any
	}{
		{name: "empty", in: "", want: nil},
		{name: "whitespace", in: "   ", want: nil},
		{name: "trimmed_valid", in: "  " + valid + "  ", want: valid},
		{name: "latest_tag", in: "latest", want: nil},
		{name: "short_hex", in: "sha256:deadbeef", want: nil},
		{name: "uppercase_hex", in: "sha256:DEADBEEFdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef", want: nil},
		{name: "wrong_algo", in: "sha512:" + strings.Repeat("a", 64), want: nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := deployImageDigestOrNull(tc.in)
			if got != tc.want {
				t.Fatalf("deployImageDigestOrNull(%q)=%v want %v", tc.in, got, tc.want)
			}
		})
	}
}
