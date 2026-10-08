package evidenceoutbox

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
)

// Deliverer is the legacy single-row projection surface. Relay will not invoke
// it unless the same value also implements TombstoneFencedDeliverer.
type Deliverer interface {
	Deliver(ctx context.Context, row OutboxRow) error
}

// TombstoneFencedDeliverer is the mandatory projection hook when the relay
// applies a row. Implementations must check the org-scoped authoritative
// tombstone/version fence and serialize that check with the projection write;
// deduplicate EventID + AggregateSeq within OrgID, and fail closed when the
// authoritative fence cannot be checked.
type TombstoneFencedDeliverer interface {
	DeliverWithTombstoneFence(ctx context.Context, row OutboxRow, fence TombstoneFence) error
}

// ErrTombstonedResource reports a terminal tombstone or stale-version decision
// from an authoritative fence check; Relay records the row as poison without
// applying it to the projection.
var ErrTombstonedResource = errors.New("evidenceoutbox: resource is tombstoned or stale")

var (
	errRedactionUnclassified  = errors.New("evidenceoutbox: payload redaction class is unclassified")
	errRedactionProhibited    = errors.New("evidenceoutbox: payload redaction class is prohibited")
	errRedactionUnsupported   = errors.New("evidenceoutbox: payload redaction class is unsupported")
	errTombstoneFenceMissing  = errors.New("evidenceoutbox: tombstone fence is required")
	errTombstoneFenceInvalid  = errors.New("evidenceoutbox: tombstone fence is invalid")
	errFencedDeliveryRequired = errors.New("evidenceoutbox: tombstone-fenced delivery is required")
)

// Relay claims pending outbox rows and delivers them at-least-once.
type Relay struct {
	db          *sql.DB
	deliverer   Deliverer
	batchSize   int
	maxAttempts int
}

// RelayConfig configures Relay batching and poison thresholds.
type RelayConfig struct {
	BatchSize   int
	MaxAttempts int
}

const (
	maxRetryBackoffSecs = 60
	maxBackoffExp       = 6
	// maxClaimBatch matches evidence_outbox_claim_pending p_limit upper bound.
	maxClaimBatch      = 256
	defaultBatch       = 32
	defaultMaxAttempts = 8
)

// NewRelay constructs a Relay. deliverer and db are required.
func NewRelay(db *sql.DB, deliverer Deliverer, cfg RelayConfig) (*Relay, error) {
	if db == nil {
		return nil, fmt.Errorf("evidenceoutbox: relay db is required")
	}
	if deliverer == nil {
		return nil, fmt.Errorf("evidenceoutbox: relay deliverer is required")
	}
	if cfg.BatchSize <= 0 {
		cfg.BatchSize = defaultBatch
	}
	if cfg.BatchSize > maxClaimBatch {
		return nil, fmt.Errorf("evidenceoutbox: batch size %d exceeds max %d", cfg.BatchSize, maxClaimBatch)
	}
	if cfg.MaxAttempts <= 0 {
		cfg.MaxAttempts = defaultMaxAttempts
	}
	return &Relay{db: db, deliverer: deliverer, batchSize: cfg.BatchSize, maxAttempts: cfg.MaxAttempts}, nil
}

// RelayBatchResult summarizes one Relay.ProcessBatch invocation.
type RelayBatchResult struct {
	Claimed   int
	Delivered int
	Failed    int
	Poisoned  int
}

// ProcessBatch claims up to BatchSize pending rows via SECURITY DEFINER helpers
// (owned by ibex_service; EXECUTE granted only to ibex_evidence_relay — not ibex_app),
// delivers via Deliverer, and marks delivered / failed / poison.
// Crash after claim but before ack leaves rows in_flight — RecoverInFlight
// returns them to pending for replay (at-least-once).
func (r *Relay) ProcessBatch(ctx context.Context) (RelayBatchResult, error) {
	rows, err := r.claimBatch(ctx)
	if err != nil {
		return RelayBatchResult{}, err
	}
	var out RelayBatchResult
	out.Claimed = len(rows)
	for _, row := range rows {
		if err := r.deliverOne(ctx, row, &out); err != nil {
			return out, err
		}
	}
	return out, nil
}

func (r *Relay) claimBatch(ctx context.Context) ([]OutboxRow, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("evidenceoutbox: relay begin: %w", err)
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()

	rows, err := claimPending(ctx, tx, r.batchSize)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("evidenceoutbox: relay claim commit: %w", err)
	}
	return rows, nil
}

func (r *Relay) deliverOne(ctx context.Context, row OutboxRow, out *RelayBatchResult) error {
	row.RedactionClass, row.TombstoneFence = parseOutboxMetadata(row.Payload)
	if err := validateOutboxRow(row); err != nil {
		return r.recordDeliveryFailure(ctx, row, out, err)
	}
	deliverer, ok := r.deliverer.(TombstoneFencedDeliverer)
	if !ok {
		return r.recordDeliveryFailure(ctx, row, out, errFencedDeliveryRequired)
	}
	if err := deliverer.DeliverWithTombstoneFence(ctx, row, *row.TombstoneFence); err != nil {
		return r.recordDeliveryFailure(ctx, row, out, err)
	}
	if err := r.markDelivered(ctx, row); err != nil {
		return err
	}
	out.Delivered++
	return nil
}

func (r *Relay) recordDeliveryFailure(ctx context.Context, row OutboxRow, out *RelayBatchResult, err error) error {
	if markErr := r.markFailure(ctx, row, err); markErr != nil {
		return markErr
	}
	// row.Attempts is already the post-claim count from claimPending.
	if row.Attempts >= r.maxAttempts || isPermanentDeliveryFailure(err) {
		out.Poisoned++
	} else {
		out.Failed++
	}
	return nil
}

func validateOutboxRow(row OutboxRow) error {
	if err := validateOutboxIdentity(row); err != nil {
		return err
	}
	class, fence := parseOutboxMetadata(row.Payload)
	if err := validateRedactionClass(class); err != nil {
		return err
	}
	if err := validateTombstoneFence(fence); err != nil {
		return err
	}
	if err := validateOutboxPayload(row); err != nil {
		return err
	}
	return nil
}

func validateOutboxIdentity(row OutboxRow) error {
	switch {
	case row.ID == uuid.Nil:
		return fmt.Errorf("evidenceoutbox: invalid row: id is required")
	case row.OrgID == uuid.Nil:
		return fmt.Errorf("evidenceoutbox: invalid row: org_id is required")
	case row.EventID == uuid.Nil:
		return fmt.Errorf("evidenceoutbox: invalid row: event_id is required")
	case strings.TrimSpace(row.AggregateID) == "":
		return fmt.Errorf("evidenceoutbox: invalid row: aggregate_id is required")
	case row.AggregateSeq <= 0:
		return fmt.Errorf("evidenceoutbox: invalid row: aggregate_seq must be positive")
	case strings.TrimSpace(row.SchemaVersion) == "":
		return fmt.Errorf("evidenceoutbox: invalid row: schema_version is required")
	case strings.TrimSpace(row.EventType) == "":
		return fmt.Errorf("evidenceoutbox: invalid row: event_type is required")
	default:
		return nil
	}
}

func parseOutboxMetadata(payload []byte) (RedactionClass, *TombstoneFence) {
	var metadata struct {
		RedactionClass RedactionClass  `json:"redaction_class"`
		TombstoneFence *TombstoneFence `json:"tombstone_fence"`
	}
	if err := json.Unmarshal(payload, &metadata); err != nil {
		return RedactionClassUnclassified, nil
	}
	if metadata.RedactionClass == "" {
		metadata.RedactionClass = RedactionClassUnclassified
	}
	return metadata.RedactionClass, metadata.TombstoneFence
}

func validateRedactionClass(class RedactionClass) error {
	switch class {
	case RedactionClassMetadata:
		return nil
	case RedactionClassUnclassified:
		return errRedactionUnclassified
	case RedactionClassProhibited:
		return errRedactionProhibited
	default:
		return fmt.Errorf("%w: %q", errRedactionUnsupported, class)
	}
}

func validateTombstoneFence(fence *TombstoneFence) error {
	if fence == nil {
		return errTombstoneFenceMissing
	}
	if strings.TrimSpace(fence.ResourceType) == "" ||
		strings.TrimSpace(fence.ResourceID) == "" || fence.ResourceVersion <= 0 {
		return errTombstoneFenceInvalid
	}
	return nil
}

func isPermanentDeliveryFailure(err error) bool {
	return errors.Is(err, errRedactionUnclassified) ||
		errors.Is(err, errRedactionProhibited) ||
		errors.Is(err, errRedactionUnsupported) ||
		errors.Is(err, errTombstoneFenceMissing) ||
		errors.Is(err, errTombstoneFenceInvalid) ||
		errors.Is(err, errFencedDeliveryRequired) ||
		errors.Is(err, ErrTombstonedResource)
}

func validateOutboxPayload(row OutboxRow) error {
	actualDigest := strings.TrimSpace(row.PayloadDigest)
	switch {
	case len(row.Payload) == 0:
		return fmt.Errorf("evidenceoutbox: invalid row: payload is required")
	case actualDigest == "":
		return fmt.Errorf("evidenceoutbox: invalid row: payload_digest is required")
	case len(actualDigest) != hex.EncodedLen(sha256.Size) || !isHexDigest(actualDigest):
		return fmt.Errorf("evidenceoutbox: invalid row: payload_digest must be a SHA-256 hex digest")
	}

	expected := sha256.Sum256(row.Payload)
	if !strings.EqualFold(actualDigest, hex.EncodeToString(expected[:])) {
		return fmt.Errorf("evidenceoutbox: invalid row: payload_digest does not match payload")
	}
	return nil
}

func isHexDigest(value string) bool {
	var decoded [sha256.Size]byte
	_, err := hex.Decode(decoded[:], []byte(value))
	return err == nil
}

// RecoverInFlight returns stale in_flight rows to pending for crash/replay.
func (r *Relay) RecoverInFlight(ctx context.Context, olderThan time.Duration) (int64, error) {
	if olderThan <= 0 {
		olderThan = 30 * time.Second
	}
	// Preserve sub-second ages (int(seconds) truncates time.Nanosecond → 0).
	secs := olderThan.Seconds()
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("evidenceoutbox: recover begin: %w", err)
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()
	var n int64
	if err := tx.QueryRowContext(ctx,
		`SELECT ibex_core.evidence_outbox_recover_in_flight($1)`, secs,
	).Scan(&n); err != nil {
		return 0, fmt.Errorf("evidenceoutbox: recover in_flight: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return n, nil
}

func claimPending(ctx context.Context, tx *sql.Tx, limit int) ([]OutboxRow, error) {
	// Cast payload to text so Scan bytes match the JSONB::text form hashed at enqueue.
	rs, err := tx.QueryContext(ctx,
		`SELECT id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
			event_type, payload::text, payload_digest, delivery_status, attempts, available_at,
			last_error, created_at, delivered_at
		FROM ibex_core.evidence_outbox_claim_pending($1)`, limit)
	if err != nil {
		return nil, fmt.Errorf("evidenceoutbox: claim: %w", err)
	}
	defer func() { _ = rs.Close() }()

	var out []OutboxRow
	for rs.Next() {
		row, err := scanOutboxRow(rs)
		if err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rs.Err()
}

func scanOutboxRow(rs *sql.Rows) (OutboxRow, error) {
	var row OutboxRow
	var delivered sql.NullTime
	var payload []byte
	if err := rs.Scan(
		&row.ID, &row.OrgID, &row.EventID, &row.AggregateID, &row.AggregateSeq,
		&row.SchemaVersion, &row.EventType, &payload, &row.PayloadDigest,
		&row.DeliveryStatus, &row.Attempts, &row.AvailableAt, &row.LastError,
		&row.CreatedAt, &delivered,
	); err != nil {
		return OutboxRow{}, fmt.Errorf("evidenceoutbox: claim scan: %w", err)
	}
	row.Payload = json.RawMessage(payload)
	row.RedactionClass, row.TombstoneFence = parseOutboxMetadata(payload)
	if delivered.Valid {
		t := delivered.Time
		row.DeliveredAt = &t
	}
	return row, nil
}

func (r *Relay) markDelivered(ctx context.Context, row OutboxRow) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()
	var n int64
	if err := tx.QueryRowContext(ctx,
		`SELECT ibex_core.evidence_outbox_mark_delivered($1, $2)`,
		row.ID, row.Attempts,
	).Scan(&n); err != nil {
		return fmt.Errorf("evidenceoutbox: mark delivered: %w", err)
	}
	if n != 1 {
		return fmt.Errorf("evidenceoutbox: stale claim ack id=%s attempts=%d affected=%d",
			row.ID, row.Attempts, n)
	}
	return tx.Commit()
}

func (r *Relay) markFailure(ctx context.Context, row OutboxRow, deliverErr error) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()
	status := StatusFailed
	if row.Attempts >= r.maxAttempts || isPermanentDeliveryFailure(deliverErr) {
		status = StatusPoison
	}
	delaySecs := retryBackoffSeconds(row.Attempts)
	if status == StatusPoison {
		delaySecs = 0
	}
	var n int64
	if err := tx.QueryRowContext(ctx,
		`SELECT ibex_core.evidence_outbox_mark_failure($1, $2, $3, $4, $5)`,
		row.ID, row.Attempts, status, truncErr(deliverErr), delaySecs,
	).Scan(&n); err != nil {
		return fmt.Errorf("evidenceoutbox: mark failure: %w", err)
	}
	if n != 1 {
		return fmt.Errorf("evidenceoutbox: stale claim failure id=%s attempts=%d affected=%d",
			row.ID, row.Attempts, n)
	}
	return tx.Commit()
}

// retryBackoffSeconds returns exponential backoff with crypto jitter, capped at maxRetryBackoffSecs.
func retryBackoffSeconds(attempts int) int {
	exp := attempts
	if exp < 0 {
		exp = 0
	}
	if exp > maxBackoffExp {
		exp = maxBackoffExp
	}
	base := 1 << exp
	if base > maxRetryBackoffSecs {
		base = maxRetryBackoffSecs
	}
	half := base / 2
	if half < 1 {
		half = 1
	}
	span := base - half + 1
	n, err := rand.Int(rand.Reader, big.NewInt(int64(span)))
	if err != nil {
		return half
	}
	jittered := half + int(n.Int64())
	if jittered < 1 {
		jittered = 1
	}
	if jittered > maxRetryBackoffSecs {
		jittered = maxRetryBackoffSecs
	}
	return jittered
}

func truncErr(err error) string {
	if err == nil {
		return ""
	}
	s := strings.ToValidUTF8(err.Error(), "\uFFFD")
	if len(s) <= 500 {
		return s
	}
	s = s[:500]
	for len(s) > 0 && !utf8.ValidString(s) {
		s = s[:len(s)-1]
	}
	return s
}
