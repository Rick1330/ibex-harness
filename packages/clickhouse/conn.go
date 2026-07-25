package clickhouse

import (
	"context"
	"fmt"

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

type chInserter struct {
	conn driver.Conn
}

// OpenInserter dials ClickHouse using CLICKHOUSE_DSN (HTTP for app ports).
func OpenInserter(dsn string) (Inserter, error) {
	opts, err := parseOptions(dsn)
	if err != nil {
		return nil, err
	}
	conn, err := clickhouse.Open(opts)
	if err != nil {
		return nil, fmt.Errorf("clickhouse open: %w", err)
	}
	ctx := context.Background()
	if err := conn.Ping(ctx); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("clickhouse ping dsn=%s: %w", RedactedDSN(dsn), err)
	}
	return &chInserter{conn: conn}, nil
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
