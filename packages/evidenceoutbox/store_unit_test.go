package evidenceoutbox

import (
	"context"
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
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WithArgs(org.String()).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_runs`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`INSERT INTO ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	res, err := store.PersistRun(context.Background(), RunInput{
		OrgID:     org,
		RequestID: "req-1",
		TraceID:   "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
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
	// run outbox
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
		RootSpanID: "rootspan1", MetricsSpanID: "assemble1",
		Spans:   []SpanInput{{SpanID: "rootspan1", OperationKind: "proxy.chat"}},
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

func TestUnit_PersistRun_RLSFails(t *testing.T) {
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
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnError(context.Canceled)
	mock.ExpectRollback()
	_, err = store.PersistRun(context.Background(), RunInput{
		OrgID: uuid.New(), RequestID: "r", TraceID: "t",
	})
	if err == nil {
		t.Fatal("expected RLS error")
	}
}

func TestUnit_PersistRun_BeginFails(t *testing.T) {
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
	mock.ExpectBegin().WillReturnError(context.DeadlineExceeded)
	_, err = store.PersistRun(context.Background(), RunInput{
		OrgID: uuid.New(), RequestID: "r", TraceID: "t",
	})
	if err == nil {
		t.Fatal("expected begin error")
	}
}
