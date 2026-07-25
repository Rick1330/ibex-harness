package clickhouse

import (
	"context"
	"fmt"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/google/uuid"
)

const insertSQL = `INSERT INTO ibex.llm_traces (
	request_id, org_id, agent_id, session_id, checkpoint_id,
	model, provider, is_streaming,
	input_tokens, output_tokens, total_tokens,
	auth_latency_ms, directive_latency_ms, provider_ttfb_ms, total_latency_ms,
	status_code, is_complete, error_code,
	requested_at, completed_at
)`

// pingTimeout bounds startup connectivity checks so proxy boot cannot hang.
// Overridable in tests.
var pingTimeout = 5 * time.Second

// batchConn is the narrow CH surface used by the inserter (testable).
type batchConn interface {
	PrepareBatch(ctx context.Context, query string, opts ...driver.PrepareBatchOption) (driver.Batch, error)
	Ping(ctx context.Context) error
	Close() error
}

type chInserter struct {
	conn batchConn
}

// openConn dials ClickHouse; overridden in tests.
var openConn = func(opts *clickhouse.Options) (batchConn, error) {
	return clickhouse.Open(opts)
}

// OpenInserter dials ClickHouse using CLICKHOUSE_DSN (HTTP for app ports).
func OpenInserter(dsn string) (Inserter, error) {
	opts, err := parseOptions(dsn)
	if err != nil {
		return nil, err
	}
	conn, err := openConn(opts)
	if err != nil {
		return nil, fmt.Errorf("clickhouse open: %w", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), pingTimeout)
	defer cancel()
	if err := conn.Ping(ctx); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("clickhouse ping (timeout=%s) dsn=%s: %w", pingTimeout, RedactedDSN(dsn), err)
	}
	return newCHInserter(conn), nil
}

func newCHInserter(conn batchConn) *chInserter {
	return &chInserter{conn: conn}
}

func (c *chInserter) InsertTraces(ctx context.Context, rows []TraceRecord) error {
	if len(rows) == 0 {
		return nil
	}
	batch, err := c.conn.PrepareBatch(ctx, insertSQL)
	if err != nil {
		return fmt.Errorf("prepare batch: %w", err)
	}
	for i := range rows {
		if err := appendTrace(batch, rows[i]); err != nil {
			return err
		}
	}
	if err := batch.Send(); err != nil {
		return fmt.Errorf("send batch: %w", err)
	}
	return nil
}

func appendTrace(batch driver.Batch, r TraceRecord) error {
	err := batch.Append(
		r.RequestID,
		r.OrgID,
		r.AgentID,
		nullableUUID(r.SessionID),
		nullableUUID(r.CheckpointID),
		r.Model,
		r.Provider,
		r.IsStreaming,
		r.InputTokens,
		r.OutputTokens,
		r.TotalTokens,
		r.AuthLatencyMs,
		r.DirectiveLatencyMs,
		r.ProviderTTFBMs,
		r.TotalLatencyMs,
		r.StatusCode,
		r.IsComplete,
		r.ErrorCode,
		r.RequestedAt.UTC(),
		r.CompletedAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("append row: %w", err)
	}
	return nil
}

func nullableUUID(id *uuid.UUID) any {
	if id == nil {
		return nil
	}
	return *id
}

func (c *chInserter) Close() error {
	return c.conn.Close()
}
