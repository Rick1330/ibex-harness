package evidenceoutbox

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/google/uuid"
)

type stubDeliverer struct {
	err error
	n   int
}

func (s *stubDeliverer) Deliver(_ context.Context, _ OutboxRow) error {
	s.n++
	return s.err
}

func TestUnit_NewRelay_RequiresDeps(t *testing.T) {
	t.Parallel()
	db, _, _ := sqlmock.New()
	defer db.Close()
	if _, err := NewRelay(nil, &stubDeliverer{}, RelayConfig{}); err == nil {
		t.Fatal("expected db error")
	}
	if _, err := NewRelay(db, nil, RelayConfig{}); err == nil {
		t.Fatal("expected deliverer error")
	}
}

func TestUnit_ProcessBatch_DeliverAndAck(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	d := &stubDeliverer{}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 2, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}

	id := uuid.New()
	org := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, org, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		[]byte(`{}`), "digest", StatusInFlight, 1, now, "", now, nil)
	mock.ExpectQuery(`UPDATE ibex_core.evidence_outbox`).WillReturnRows(rows)
	mock.ExpectCommit()

	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core.evidence_outbox`).
		WithArgs(StatusDelivered, id, StatusInFlight, 1).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Claimed != 1 || res.Delivered != 1 || d.n != 1 {
		t.Fatalf("res=%+v deliveries=%d", res, d.n)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_ProcessBatch_DeliverFailureMarksFailed(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	d := &stubDeliverer{err: errors.New("sink down")}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: 5})
	if err != nil {
		t.Fatal(err)
	}

	id := uuid.New()
	org := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, org, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		[]byte(`{}`), "digest", StatusInFlight, 1, now, "", now, nil)
	mock.ExpectQuery(`UPDATE ibex_core.evidence_outbox`).WillReturnRows(rows)
	mock.ExpectCommit()

	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core.evidence_outbox`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Failed != 1 || res.Poisoned != 0 {
		t.Fatalf("res=%+v", res)
	}
}

func TestUnit_ProcessBatch_PoisonAtMaxAttempts(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	d := &stubDeliverer{err: errors.New("still down")}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: 2})
	if err != nil {
		t.Fatal(err)
	}

	id := uuid.New()
	org := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, org, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		[]byte(`{}`), "digest", StatusInFlight, 2, now, "", now, nil)
	mock.ExpectQuery(`UPDATE ibex_core.evidence_outbox`).WillReturnRows(rows)
	mock.ExpectCommit()

	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(`UPDATE ibex_core.evidence_outbox`).
		WithArgs(StatusPoison, sqlmock.AnyArg(), sqlmock.AnyArg(), id, StatusInFlight, 2).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Poisoned != 1 {
		t.Fatalf("res=%+v", res)
	}
}

func TestUnit_MarkDelivered_StaleWorkerNoOp(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	relay, err := NewRelay(db, &stubDeliverer{}, RelayConfig{})
	if err != nil {
		t.Fatal(err)
	}
	id := uuid.New()
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT set_config`).WillReturnResult(sqlmock.NewResult(0, 1))
	// Conditional UPDATE matches 0 rows (stale claim).
	mock.ExpectExec(`UPDATE ibex_core.evidence_outbox`).
		WithArgs(StatusDelivered, id, StatusInFlight, 1).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectCommit()

	if err := relay.markDelivered(context.Background(), OutboxRow{ID: id, Attempts: 1}); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
