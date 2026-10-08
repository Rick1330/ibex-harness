package evidenceoutbox

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

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

func validPayloadDigest(payload []byte) string {
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:])
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
	if _, err := NewRelay(db, &stubDeliverer{}, RelayConfig{BatchSize: maxClaimBatch + 1}); err == nil {
		t.Fatal("expected batch size error")
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

type idempotentReplayDeliverer struct {
	deliveries int
	effects    map[string]int
}

func (d *idempotentReplayDeliverer) Deliver(_ context.Context, row OutboxRow) error {
	d.deliveries++
	if d.effects == nil {
		d.effects = map[string]int{}
	}
	key := row.EventID.String() + ":" + fmt.Sprint(row.AggregateSeq)
	if d.effects[key] == 0 {
		d.effects[key] = 1
	}
	return nil
}

func TestUnit_ProcessBatch_AckLossReplaysWithIdempotentEffect(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	d := &idempotentReplayDeliverer{}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}
	id := uuid.New()
	org := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	row := func(attempts int) *sqlmock.Rows {
		return sqlmock.NewRows([]string{
			"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
			"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
			"last_error", "created_at", "delivered_at",
		}).AddRow(id, org, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
			[]byte(`{}`), validPayloadDigest([]byte(`{}`)), StatusInFlight, attempts, now, "", now, nil)
	}

	// The sink applies the event, but the relay loses the acknowledgement.
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(1).WillReturnRows(row(1))
	mock.ExpectCommit()
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_delivered`).WithArgs(id, 1).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(0))
	mock.ExpectRollback()
	if _, err := relay.ProcessBatch(context.Background()); err == nil {
		t.Fatal("expected lost acknowledgement error")
	}

	// A recovered claim is delivered again; the sink's stable identity makes the effect idempotent.
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(1).WillReturnRows(row(2))
	mock.ExpectCommit()
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_delivered`).WithArgs(id, 2).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(1))
	mock.ExpectCommit()
	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Delivered != 1 || d.deliveries != 2 || len(d.effects) != 1 {
		t.Fatalf("replay semantics: result=%+v deliveries=%d effects=%d", res, d.deliveries, len(d.effects))
	}
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
		[]byte(`{}`), validPayloadDigest([]byte(`{}`)), StatusInFlight, 1, now, "", now, nil)
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
	cases := []deliverFailureCase{
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
			runDeliverFailureCase(t, tc)
		})
	}
}

type deliverFailureCase struct {
	name         string
	attempts     int
	maxAttempts  int
	wantFailed   int
	wantPoisoned int
	markStatus   string
}

func runDeliverFailureCase(t *testing.T, tc deliverFailureCase) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	d := &stubDeliverer{err: errors.New("sink down")}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: tc.maxAttempts})
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
		[]byte(`{}`), validPayloadDigest([]byte(`{}`)), StatusInFlight, tc.attempts, now, "", now, nil)
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(1).WillReturnRows(rows)
	mock.ExpectCommit()

	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_failure`).
		WithArgs(id, tc.attempts, tc.markStatus, "sink down", sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(1))
	mock.ExpectCommit()

	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if res.Failed != tc.wantFailed || res.Poisoned != tc.wantPoisoned {
		t.Fatalf("res=%+v want failed=%d poisoned=%d", res, tc.wantFailed, tc.wantPoisoned)
	}
}

func TestUnit_ProcessBatch_InvalidTenantRowNeverReachesSink(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	d := &stubDeliverer{}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: 1})
	if err != nil {
		t.Fatal(err)
	}

	id := uuid.New()
	eventID := uuid.New()
	now := time.Now()
	mock.ExpectBegin()
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, uuid.Nil, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		[]byte(`{}`), validPayloadDigest([]byte(`{}`)), StatusInFlight, 1, now, "", now, nil)
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(1).WillReturnRows(rows)
	mock.ExpectCommit()
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_failure`).
		WithArgs(id, 1, StatusPoison, "evidenceoutbox: invalid row: org_id is required", sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(1))
	mock.ExpectCommit()

	res, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	assertPoisonedWithoutDelivery(t, res, d)
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func assertPoisonedWithoutDelivery(t *testing.T, res RelayBatchResult, d *stubDeliverer) {
	t.Helper()
	if res.Delivered != 0 {
		t.Fatalf("delivered=%d want 0", res.Delivered)
	}
	if res.Failed != 0 {
		t.Fatalf("failed=%d want 0", res.Failed)
	}
	if res.Poisoned != 1 {
		t.Fatalf("poisoned=%d want 1", res.Poisoned)
	}
	if d.n != 0 {
		t.Fatalf("deliveries=%d want 0", d.n)
	}
}

func TestUnit_ValidateOutboxRow_RejectsMalformedDigest(t *testing.T) {
	t.Parallel()
	row := OutboxRow{ID: uuid.New(), OrgID: uuid.New(), EventID: uuid.New(), AggregateID: "agg", AggregateSeq: 1, SchemaVersion: SchemaVersion, EventType: EventTypeRunCommitted, Payload: []byte(`{}`), PayloadDigest: "not-a-sha256-digest"}
	if err := validateOutboxRow(row); err == nil || !strings.Contains(err.Error(), "payload_digest") {
		t.Fatalf("err=%v want payload digest validation error", err)
	}
}

func TestUnit_ValidateOutboxRow_RejectsDigestMismatch(t *testing.T) {
	t.Parallel()
	payload := []byte(`{"value":"trusted"}`)
	row := OutboxRow{
		ID: uuid.New(), OrgID: uuid.New(), EventID: uuid.New(), AggregateID: "agg", AggregateSeq: 1,
		SchemaVersion: SchemaVersion, EventType: EventTypeRunCommitted,
		Payload: payload, PayloadDigest: validPayloadDigest([]byte(`{"value":"tampered"}`)),
	}
	if err := validateOutboxRow(row); err == nil || !strings.Contains(err.Error(), "does not match payload") {
		t.Fatalf("err=%v want payload digest mismatch", err)
	}
}

func TestUnit_ValidateOutboxRow_AcceptsUppercaseDigest(t *testing.T) {
	t.Parallel()
	payload := []byte(`{"value":"trusted"}`)
	row := OutboxRow{
		ID: uuid.New(), OrgID: uuid.New(), EventID: uuid.New(), AggregateID: "agg", AggregateSeq: 1,
		SchemaVersion: SchemaVersion, EventType: EventTypeRunCommitted,
		Payload: payload, PayloadDigest: strings.ToUpper(validPayloadDigest(payload)),
	}
	if err := validateOutboxRow(row); err != nil {
		t.Fatalf("uppercase digest should be accepted: %v", err)
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

func TestUnit_TruncErr_UTF8SafeCap(t *testing.T) {
	t.Parallel()
	if got := truncErr(nil); got != "" {
		t.Fatalf("nil=%q", got)
	}
	// Invalid UTF-8 byte sequence should be replaced, not passed through.
	raw := errors.New("bad\xfftrail")
	got := truncErr(raw)
	if !utf8.ValidString(got) {
		t.Fatalf("invalid utf8: %q", got)
	}
	if !strings.Contains(got, "bad") || !strings.Contains(got, "trail") {
		t.Fatalf("got=%q", got)
	}
	// Cap at 500 bytes without splitting a multibyte rune.
	long := strings.Repeat("a", 498) + "日本語"
	got = truncErr(errors.New(long))
	if len(got) > 500 {
		t.Fatalf("len=%d", len(got))
	}
	if !utf8.ValidString(got) {
		t.Fatalf("split rune: %q", got)
	}
}
