package clickhouse

import "context"

// Inserter inserts trace batches into ClickHouse. Tests inject fakes.
type Inserter interface {
	InsertTraces(ctx context.Context, rows []TraceRecord) error
	Close() error
}
