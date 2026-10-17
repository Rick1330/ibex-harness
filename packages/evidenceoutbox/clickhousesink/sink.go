// Package clickhousesink contains a non-production evidence projection pilot.
// ClickHouse is deliberately treated as a projection, never as lifecycle
// authority or an acknowledgement source.
package clickhousesink

import (
	"context"
	"fmt"
	"sync"
	"time"

	clickhouse "github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

const insertQuery = `INSERT INTO ibex.evidence_events (
	org_id, event_id, aggregate_id, aggregate_seq, schema_version, event_type,
	redaction_class, resource_type, resource_id, resource_version, payload, received_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`

// FenceChecker is implemented by the authoritative PostgreSQL lifecycle owner.
// The ClickHouse sink refuses to project a row when this check is unavailable.
type FenceChecker interface {
	CheckFence(ctx context.Context, orgID uuid.UUID, fence evidenceoutbox.TombstoneFence) error
}

type sinkConn interface {
	QueryRow(ctx context.Context, query string, args ...any) driver.Row
	Exec(ctx context.Context, query string, args ...any) error
	Close() error
}

// Sink is an at-least-once ClickHouse projection deliverer. Dedupe is checked
// under the tenant predicate (org_id, event_id, aggregate_seq); the table's
// ReplacingMergeTree provides eventual duplicate collapse as a second guard.
type Sink struct {
	conn   sinkConn
	fences FenceChecker
	mu     sync.Mutex
	now    func() time.Time
}

// New constructs a sink. A nil fence checker is rejected because ClickHouse
// cannot certify tombstone/version authority itself.
func New(conn sinkConn, fences FenceChecker) (*Sink, error) {
	if conn == nil {
		return nil, fmt.Errorf("clickhousesink: connection is required")
	}
	if fences == nil {
		return nil, fmt.Errorf("clickhousesink: authoritative fence checker is required")
	}
	return &Sink{conn: conn, fences: fences, now: time.Now}, nil
}

// Open parses a clickhouse-go DSN, pings the server, and constructs a sink.
func Open(ctx context.Context, dsn string, fences FenceChecker) (*Sink, error) {
	options, err := clickhouse.ParseDSN(dsn)
	if err != nil {
		return nil, fmt.Errorf("clickhousesink: parse dsn: %w", err)
	}
	conn, err := clickhouse.Open(options)
	if err != nil {
		return nil, fmt.Errorf("clickhousesink: open: %w", err)
	}
	if err := conn.Ping(ctx); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("clickhousesink: ping: %w", err)
	}
	sink, err := New(conn, fences)
	if err != nil {
		_ = conn.Close()
		return nil, err
	}
	return sink, nil
}

// Close closes the underlying ClickHouse connection.
func (s *Sink) Close() error { return s.conn.Close() }

// DeliverWithTombstoneFence implements evidenceoutbox.TombstoneFencedDeliverer.
func (s *Sink) DeliverWithTombstoneFence(ctx context.Context, row evidenceoutbox.OutboxRow, fence evidenceoutbox.TombstoneFence) error {
	if err := validateRow(row, fence); err != nil {
		return err
	}
	if err := s.fences.CheckFence(ctx, row.OrgID, fence); err != nil {
		return fmt.Errorf("clickhousesink: authoritative fence check: %w", err)
	}

	// Serialize this process's check+insert. Cross-process correctness remains
	// eventual via the ReplacingMergeTree key and must not be mistaken for an
	// atomic lifecycle transaction.
	s.mu.Lock()
	defer s.mu.Unlock()
	var count uint64
	if err := s.conn.QueryRow(ctx, `SELECT count() FROM ibex.evidence_events WHERE org_id = ? AND event_id = ? AND aggregate_seq = ?`, row.OrgID, row.EventID, row.AggregateSeq).Scan(&count); err != nil {
		return fmt.Errorf("clickhousesink: dedupe lookup: %w", err)
	}
	if count > 0 {
		return nil
	}
	if err := s.conn.Exec(ctx, insertQuery,
		row.OrgID, row.EventID, row.AggregateID, row.AggregateSeq, row.SchemaVersion,
		row.EventType, row.RedactionClass, fence.ResourceType, fence.ResourceID,
		fence.ResourceVersion, string(row.Payload), s.now().UTC()); err != nil {
		return fmt.Errorf("clickhousesink: insert projection: %w", err)
	}
	return nil
}

func validateRow(row evidenceoutbox.OutboxRow, fence evidenceoutbox.TombstoneFence) error {
	if err := validateIdentity(row); err != nil {
		return err
	}
	if err := validatePayload(row); err != nil {
		return err
	}
	return validateFence(fence)
}

func validateIdentity(row evidenceoutbox.OutboxRow) error {
	if row.OrgID == uuid.Nil {
		return fmt.Errorf("clickhousesink: invalid tenant identity")
	}
	if row.EventID == uuid.Nil {
		return fmt.Errorf("clickhousesink: invalid event identity")
	}
	if row.AggregateSeq <= 0 {
		return fmt.Errorf("clickhousesink: invalid tenant/event identity")
	}
	return nil
}

func validatePayload(row evidenceoutbox.OutboxRow) error {
	if row.SchemaVersion == "" {
		return fmt.Errorf("clickhousesink: incomplete outbox row")
	}
	if row.EventType == "" {
		return fmt.Errorf("clickhousesink: incomplete outbox row")
	}
	if len(row.Payload) == 0 {
		return fmt.Errorf("clickhousesink: incomplete outbox row")
	}
	return nil
}

func validateFence(fence evidenceoutbox.TombstoneFence) error {
	if fence.ResourceType == "" {
		return fmt.Errorf("clickhousesink: invalid tombstone fence")
	}
	if fence.ResourceID == "" {
		return fmt.Errorf("clickhousesink: invalid tombstone fence")
	}
	if fence.ResourceVersion <= 0 {
		return fmt.Errorf("clickhousesink: invalid tombstone fence")
	}
	return nil
}
