package clickhouse

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
)

const (
	defaultMaxBatchSize         = 500
	defaultMaxBufferSize        = 2000 // 4x default batch; bounds memory under slow CH
	defaultFlushInterval        = 200 * time.Millisecond
	defaultFlushTimeout         = 5 * time.Second
	defaultShutdownFlushTimeout = 10 * time.Second
)

// Config configures a Writer.
type Config struct {
	DSN string
	// MaxBatchSize triggers a flush when the buffer reaches this many rows.
	MaxBatchSize int
	// MaxBufferSize is a hard cap on queued rows. When exceeded, oldest rows
	// are dropped (best-effort delivery) so memory stays bounded.
	MaxBufferSize int
	// FlushInterval is the periodic background flush cadence.
	FlushInterval time.Duration
	// FlushTimeout bounds each periodic/size-triggered flush attempt.
	FlushTimeout time.Duration
	// ShutdownFlushTimeout bounds the final drain in Close/Shutdown.
	ShutdownFlushTimeout time.Duration
	Logger               *logger.Logger
	// Metrics records flush outcomes; nil disables metric emission.
	Metrics FlushMetrics
}

// FlushMetrics observes batch flush outcomes (implemented by packages/metrics).
type FlushMetrics interface {
	IncClickHouseFlush(result string)
	AddClickHouseFlushRows(n int)
	AddClickHouseDroppedRows(n int)
	ObserveClickHouseFlushSeconds(seconds float64)
}

// ApplyDefaults fills zero-valued fields.
func (c *Config) ApplyDefaults() {
	if c.MaxBatchSize <= 0 {
		c.MaxBatchSize = defaultMaxBatchSize
	}
	if c.MaxBufferSize <= 0 {
		c.MaxBufferSize = defaultMaxBufferSize
	}
	if c.MaxBufferSize < c.MaxBatchSize {
		c.MaxBufferSize = c.MaxBatchSize
	}
	if c.FlushInterval <= 0 {
		c.FlushInterval = defaultFlushInterval
	}
	if c.FlushTimeout <= 0 {
		c.FlushTimeout = defaultFlushTimeout
	}
	if c.ShutdownFlushTimeout <= 0 {
		c.ShutdownFlushTimeout = defaultShutdownFlushTimeout
	}
}
