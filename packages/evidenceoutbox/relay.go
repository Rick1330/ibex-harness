package evidenceoutbox

import (
	"context"
	"crypto/rand"
	"database/sql"
	"fmt"
	"math/big"
	"strings"
	"time"
	"unicode/utf8"
)

// Deliverer delivers one outbox row to a durable projection (ClickHouse, Redis, etc.).
// Implementations must be idempotent on EventID + AggregateSeq.
type Deliverer interface {
	Deliver(ctx context.Context, row OutboxRow) error
}

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
// (owned by ibex_service; ibex_app cannot assume that role), delivers via Deliverer,
// and marks delivered / failed / poison.
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
	if err := r.deliverer.Deliver(ctx, row); err != nil {
		if markErr := r.markFailure(ctx, row, err); markErr != nil {
			return markErr
		}
		// row.Attempts is already the post-claim count from claimPending.
		if row.Attempts >= r.maxAttempts {
			out.Poisoned++
		} else {
			out.Failed++
		}
		return nil
	}
	if err := r.markDelivered(ctx, row); err != nil {
		return err
	}
	out.Delivered++
	return nil
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
	rs, err := tx.QueryContext(ctx,
		`SELECT id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
			event_type, payload, payload_digest, delivery_status, attempts, available_at,
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
	if err := rs.Scan(
		&row.ID, &row.OrgID, &row.EventID, &row.AggregateID, &row.AggregateSeq,
		&row.SchemaVersion, &row.EventType, &row.Payload, &row.PayloadDigest,
		&row.DeliveryStatus, &row.Attempts, &row.AvailableAt, &row.LastError,
		&row.CreatedAt, &delivered,
	); err != nil {
		return OutboxRow{}, fmt.Errorf("evidenceoutbox: claim scan: %w", err)
	}
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
	if row.Attempts >= r.maxAttempts {
		status = StatusPoison
	}
	delaySecs := retryBackoffSeconds(row.Attempts)
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
