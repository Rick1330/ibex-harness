package clickhouse

import "errors"

// ErrWriterClosed is returned when Write is called after Close.
var ErrWriterClosed = errors.New("clickhouse writer closed")

// ErrInvalidRecord is returned when a TraceRecord fails validation.
var ErrInvalidRecord = errors.New("clickhouse invalid trace record")
