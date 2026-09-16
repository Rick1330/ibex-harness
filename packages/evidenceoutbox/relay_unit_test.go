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
	defer func() { _ = db.Close() }()
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
	defer func() { _ = db.Close() }()
	d := &stubDeliverer{}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 2, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}
	_ = expectClaimAndAck(mock)
	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	assertDeliveredOnce(t, res, d)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func expectClaimAndAck(mock sqlmock.Sqlmock) uuid.UUID {
	id := uuid.New()
	org := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	mock.ExpectBegin()
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, org, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		[]byte(`{}`), "digest", StatusInFlight, 1, now, "", now, nil)
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(2).WillReturnRows(rows)
	mock.ExpectCommit()
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_delivered`).
		WithArgs(id, 1).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(1))
	mock.ExpectCommit()
	return id
}

func assertDeliveredOnce(t *testing.T, res RelayBatchResult, d *stubDeliverer) {
	t.Helper()
	if res.Claimed != 1 {
		t.Fatalf("claimed=%d", res.Claimed)
	}
	if res.Delivered != 1 {
		t.Fatalf("delivered=%d", res.Delivered)
	}
	if d.n != 1 {
		t.Fatalf("deliveries=%d", d.n)
	}
}

func TestUnit_ProcessBatch_DeliverFailureOutcomes(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name         string
		attempts     int
		maxAttempts  int
		wantFailed   int
		wantPoisoned int
		markStatus   string
	}{
		{
			name: "failed_below_max", attempts: 1, maxAttempts: 5,
			wantFailed: 1, markStatus: StatusFailed,
		},
		{
			name: "poison_at_max", attempts: 2, maxAttempts: 2,
			wantPoisoned: 1, markStatus: StatusPoison,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runDeliverFailureCase(t, tc.attempts, tc.maxAttempts, tc.markStatus, tc.wantFailed, tc.wantPoisoned)
		})
	}
}

func runDeliverFailureCase(t *testing.T, attempts, maxAttempts int, markStatus string, wantFailed, wantPoisoned int) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	d := &stubDeliverer{err: errors.New("sink down")}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: maxAttempts})
	if err != nil {
		t.Fatal(err)
	}

	id := uuid.New()
	org := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	mock.ExpectBegin()
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, org, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		[]byte(`{}`), "digest", StatusInFlight, attempts, now, "", now, nil)
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(1).WillReturnRows(rows)
	mock.ExpectCommit()

	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_failure`).
		WithArgs(id, attempts, markStatus, "sink down", sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(1))
	mock.ExpectCommit()

	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Failed != wantFailed || res.Poisoned != wantPoisoned {
		t.Fatalf("res=%+v want failed=%d poisoned=%d", res, wantFailed, wantPoisoned)
	}
}

func TestUnit_MarkDelivered_StaleWorkerErrors(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	relay, err := NewRelay(db, &stubDeliverer{}, RelayConfig{})
	if err != nil {
		t.Fatal(err)
	}
	id := uuid.New()
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_delivered`).
		WithArgs(id, 1).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(0))
	mock.ExpectRollback()

	if err := relay.markDelivered(context.Background(), OutboxRow{ID: id, Attempts: 1}); err == nil {
		t.Fatal("expected stale claim error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
