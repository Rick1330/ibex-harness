package evidenceoutbox

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Sink delivers one outbox row to a durable projection (ClickHouse, Redis, etc.).
// Implementations must be idempotent on EventID + AggregateSeq.
type Sink interface {
	Deliver(ctx context.Context, row OutboxRow) error
}

// Relay claims pending outbox rows and delivers them at-least-once.
type Relay struct {
	db          *sql.DB
	sink        Sink
	batchSize   int
	maxAttempts int
}

// RelayConfig configures Relay batching and poison thresholds.
type RelayConfig struct {
	BatchSize   int
	MaxAttempts int
}

// NewRelay constructs a Relay. sink and db are required.
func NewRelay(db *sql.DB, sink Sink, cfg RelayConfig) (*Relay, error) {
	if db == nil {
		return nil, fmt.Errorf("evidenceoutbox: relay db is required")
	}
	if sink == nil {
		return nil, fmt.Errorf("evidenceoutbox: relay sink is required")
	}
	if cfg.BatchSize <= 0 {
		cfg.BatchSize = 32
	}
	if cfg.MaxAttempts <= 0 {
		cfg.MaxAttempts = 8
	}
	return &Relay{db: db, sink: sink, batchSize: cfg.BatchSize, maxAttempts: cfg.MaxAttempts}, nil
}

// RelayBatchResult summarizes one Relay.ProcessBatch invocation.
type RelayBatchResult struct {
	Claimed   int
	Delivered int
	Failed    int
	Poisoned  int
}

// ProcessBatch claims up to BatchSize pending rows (service-account RLS),
// delivers via Sink, and marks delivered / failed / poison.
// Crash after claim but before ack leaves rows in_flight — RecoverInFlight
// returns them to pending for replay (at-least-once).
func (r *Relay) ProcessBatch(ctx context.Context) (RelayBatchResult, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return RelayBatchResult{}, fmt.Errorf("evidenceoutbox: relay begin: %w", err)
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()

	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return RelayBatchResult{}, err
	}

	rows, err := claimPending(ctx, tx, r.batchSize)
	if err != nil {
		return RelayBatchResult{}, err
	}
	if err := tx.Commit(); err != nil {
		return RelayBatchResult{}, fmt.Errorf("evidenceoutbox: relay claim commit: %w", err)
	}

	var out RelayBatchResult
	out.Claimed = len(rows)
	for _, row := range rows {
		if err := r.sink.Deliver(ctx, row); err != nil {
			if markErr := r.markFailure(ctx, row, err); markErr != nil {
				return out, markErr
			}
			if row.Attempts+1 >= r.maxAttempts {
				out.Poisoned++
			} else {
				out.Failed++
			}
			continue
		}
		if err := r.markDelivered(ctx, row.ID); err != nil {
			return out, err
		}
		out.Delivered++
	}
	return out, nil
}

// RecoverInFlight returns stale in_flight rows to pending for crash/replay.
func (r *Relay) RecoverInFlight(ctx context.Context, olderThan time.Duration) (int64, error) {
	if olderThan <= 0 {
		olderThan = 30 * time.Second
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
  AND created_at < NOW() - ($3::text || ' seconds')::interval
`, StatusPending, StatusInFlight, fmt.Sprintf("%d", int(olderThan.Seconds())))
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
SET delivery_status = $1, attempts = attempts + 1
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
	defer rs.Close()

	var out []OutboxRow
	for rs.Next() {
		var row OutboxRow
		var delivered sql.NullTime
		if err := rs.Scan(
			&row.ID, &row.OrgID, &row.EventID, &row.AggregateID, &row.AggregateSeq,
			&row.SchemaVersion, &row.EventType, &row.Payload, &row.PayloadDigest,
			&row.DeliveryStatus, &row.Attempts, &row.AvailableAt, &row.LastError,
			&row.CreatedAt, &delivered,
		); err != nil {
			return nil, fmt.Errorf("evidenceoutbox: claim scan: %w", err)
		}
		if delivered.Valid {
			t := delivered.Time
			row.DeliveredAt = &t
		}
		out = append(out, row)
	}
	return out, rs.Err()
}

func (r *Relay) markDelivered(ctx context.Context, id uuid.UUID) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	//nolint:errcheck
	defer func() { _ = tx.Rollback() }()
	if err := setServiceAccountRLS(ctx, tx); err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `
UPDATE ibex_core.evidence_outbox
SET delivery_status = $1, delivered_at = NOW(), last_error = NULL
WHERE id = $2`, StatusDelivered, id)
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
	backoff := time.Duration(row.Attempts) * time.Second
	_, err = tx.ExecContext(ctx, `
UPDATE ibex_core.evidence_outbox
SET delivery_status = $1, last_error = $2, available_at = NOW() + $3::interval
WHERE id = $4`, status, truncErr(deliverErr), fmt.Sprintf("%d seconds", int(backoff.Seconds())), row.ID)
	if err != nil {
		return fmt.Errorf("evidenceoutbox: mark failure: %w", err)
	}
	return tx.Commit()
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
