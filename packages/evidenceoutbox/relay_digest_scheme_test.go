package evidenceoutbox

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Rick1330/ibex-harness/packages/canonicaljson"
	"github.com/google/uuid"
)

func validPayloadDigest(payload []byte) string {
	_, digest, err := canonicaljson.Digest(payload)
	if err != nil {
		return strings.Repeat("0", 64)
	}
	return digest
}

func legacyJSONBDigest(payload []byte) string {
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func digestSchemeRow(payload []byte, scheme, digest string) OutboxRow {
	return OutboxRow{Payload: payload, PayloadDigestScheme: scheme, PayloadDigest: digest}
}

func TestUnit_ProcessBatch_DeliversLegacyJSONBDigest(t *testing.T) {
	t.Parallel()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = db.Close() }()
	d := &stubDeliverer{}
	relay, err := NewRelay(db, d, RelayConfig{BatchSize: 1, MaxAttempts: 3})
	if err != nil {
		t.Fatal(err)
	}

	id, orgID, eventID := uuid.New(), uuid.New(), uuid.New()
	now := time.Now()
	payload := []byte(`{"redaction_class": "metadata", "tombstone_fence": {"resource_id": "mem-1", "resource_type": "memory", "resource_version": 1}}`)
	mock.ExpectBegin()
	rows := sqlmock.NewRows([]string{
		"id", "org_id", "event_id", "aggregate_id", "aggregate_seq", "schema_version",
		"event_type", "payload", "payload_digest", "payload_digest_scheme", "delivery_status", "attempts", "available_at",
		"last_error", "created_at", "delivered_at",
	}).AddRow(id, orgID, eventID, "agg", int64(1), SchemaVersion, EventTypeRunCommitted,
		payload, legacyJSONBDigest(payload), PayloadDigestSchemePostgresJSONBText,
		StatusInFlight, 1, now, "", now, nil)
	mock.ExpectQuery(`evidence_outbox_claim_pending`).WithArgs(1).WillReturnRows(rows)
	mock.ExpectCommit()
	mock.ExpectBegin()
	mock.ExpectQuery(`evidence_outbox_mark_delivered`).WithArgs(id, 1).
		WillReturnRows(sqlmock.NewRows([]string{"n"}).AddRow(1))
	mock.ExpectCommit()

	result, err := relay.ProcessBatch(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if result.Delivered != 1 {
		t.Fatalf("legacy retry delivered=%d want 1", result.Delivered)
	}
	if d.n != 1 {
		t.Fatalf("legacy retry deliveries=%d want 1", d.n)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_ValidateOutboxPayloadAcceptsLegacyJSONBTextDigest(t *testing.T) {
	t.Parallel()
	payload := []byte(`{"a": 1}`)
	row := digestSchemeRow(payload, PayloadDigestSchemePostgresJSONBText, legacyJSONBDigest(payload))
	if err := validateOutboxPayload(row); err != nil {
		t.Fatalf("legacy JSONB digest rejected: %v", err)
	}
}

func TestUnit_ValidateOutboxPayloadAcceptsJCSV1Digest(t *testing.T) {
	t.Parallel()
	payload := []byte(`{"a": 1}`)
	row := digestSchemeRow(payload, PayloadDigestSchemeJCSV1, validPayloadDigest(payload))
	if err := validateOutboxPayload(row); err != nil {
		t.Fatalf("JCS digest rejected: %v", err)
	}
}

func TestUnit_ValidateOutboxPayloadRejectsInvalidSchemesAndPayloads(t *testing.T) {
	t.Parallel()
	payload := []byte(`{"a": 1}`)
	tests := []struct {
		name string
		row  OutboxRow
		want string
	}{
		{
			name: "legacy digest under JCS",
			row:  digestSchemeRow(payload, PayloadDigestSchemeJCSV1, legacyJSONBDigest(payload)),
			want: "does not match payload",
		},
		{
			name: "unsupported digest scheme",
			row:  digestSchemeRow(payload, "unknown/v1", legacyJSONBDigest(payload)),
			want: "unsupported payload_digest_scheme",
		},
		{
			name: "duplicate keys for JCS",
			row: digestSchemeRow(
				[]byte(`{"duplicate":1,"duplicate":2}`),
				PayloadDigestSchemeJCSV1,
				strings.Repeat("0", 64),
			),
			want: "payload is not canonicalizable",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := validateOutboxPayload(tc.row)
			if err == nil {
				t.Fatal("invalid payload or digest scheme was accepted")
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("validation error=%v want substring %q", err, tc.want)
			}
		})
	}
}
