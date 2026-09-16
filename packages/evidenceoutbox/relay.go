package evidenceoutbox

import (
	"context"
	"crypto/rand"
	"database/sql"
	"fmt"
	"math/big"
	"time"
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

// NewRelay constructs a Relay. deliverer and db are required.
func NewRelay(db *sql.DB, deliverer Deliverer, cfg RelayConfig) (*Relay, error) {
	if db == nil {
		return nil, fmt.Errorf("evidenceoutbox: relay db is required")
	}
	if deliverer == nil {
		return nil, fmt.Errorf("evidenceoutbox: relay deliverer is required")
	}
	if cfg.BatchSize <= 0 {
		cfg.BatchSize = 32
	}
	if cfg.MaxAttempts <= 0 {
		cfg.MaxAttempts = 8
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

const (
	maxRetryBackoffSecs = 60
	maxBackoffExp       = 6
)

// ProcessBatch claims up to BatchSize pending rows (service-account RLS),
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

	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return nil, err
	}
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
	secs := int(olderThan.Seconds())
	if secs < 0 {
		secs = 0
	}
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("evidenceoutbox: recover begin: %w", err)
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()
	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return 0, err
	}
	res, err := tx.ExecContext(ctx, `
UPDATE ibex_core.evidence_outbox
SET delivery_status = $1
WHERE delivery_status = $2
  AND claimed_at IS NOT NULL
  AND claimed_at < NOW() - make_interval(secs => $3::int)
`, StatusPending, StatusInFlight, secs)
	if err != nil {
		return 0, fmt.Errorf("evidenceoutbox: recover in_flight: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	n, _ := res.RowsAffected()
	return n, nil
}

func claimPending(ctx context.Context, tx *sql.Tx, limit int) ([]OutboxRow, error) {
	q := `
UPDATE ibex_core.evidence_outbox o
SET delivery_status = $1, attempts = attempts + 1, claimed_at = NOW()
WHERE o.id IN (
	SELECT id FROM ibex_core.evidence_outbox
	WHERE delivery_status IN ($2, $3)
	  AND available_at <= NOW()
	ORDER BY available_at, created_at
	FOR UPDATE SKIP LOCKED
	LIMIT $4
)
RETURNING id, org_id, event_id, aggregate_id, aggregate_seq, schema_version,
	event_type, payload, payload_digest, delivery_status, attempts, available_at,
	COALESCE(last_error, ''), created_at, delivered_at
`
	rs, err := tx.QueryContext(ctx, q, StatusInFlight, StatusPending, StatusFailed, limit)
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
	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return err
	}
	// Only ack if this claim is still the active in_flight owner (attempts match).
	_, err = tx.ExecContext(ctx, `
UPDATE ibex_core.evidence_outbox
SET delivery_status = $1, delivered_at = NOW(), last_error = NULL
WHERE id = $2 AND delivery_status = $3 AND attempts = $4`,
		StatusDelivered, row.ID, StatusInFlight, row.Attempts)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: mark delivered: %w", err)
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
	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return err
	}
	status := StatusFailed
	if row.Attempts >= r.maxAttempts {
		status = StatusPoison
	}
	delaySecs := retryBackoffSeconds(row.Attempts)
	_, err = tx.ExecContext(ctx, `
UPDATE ibex_core.evidence_outbox
SET delivery_status = $1, last_error = $2, available_at = NOW() + make_interval(secs => $3::int)
WHERE id = $4 AND delivery_status = $5 AND attempts = $6`,
		status, truncErr(deliverErr), delaySecs, row.ID, StatusInFlight, row.Attempts)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: mark failure: %w", err)
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
	s := err.Error()
	if len(s) > 512 {
		return s[:512]
	}
	return s
}
