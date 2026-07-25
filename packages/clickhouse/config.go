package clickhouse

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
)

const (
	defaultMaxBatchSize         = 500
	defaultFlushInterval        = 200 * time.Millisecond
	defaultShutdownFlushTimeout = 10 * time.Second
)

// Config configures a Writer.
type Config struct {
	DSN                  string
	MaxBatchSize         int
	FlushInterval        time.Duration
	ShutdownFlushTimeout time.Duration
	Logger               *logger.Logger
	// Metrics records flush outcomes; nil disables metric emission.
	Metrics FlushMetrics
}

// FlushMetrics observes batch flush outcomes (implemented by packages/metrics).
type FlushMetrics interface {
	IncClickHouseFlush(result string)
	AddClickHouseFlushRows(n int)
	ObserveClickHouseFlushSeconds(seconds float64)
}

// ApplyDefaults fills zero-valued fields.
func (c *Config) ApplyDefaults() {
	if c.MaxBatchSize <= 0 {
		c.MaxBatchSize = defaultMaxBatchSize
	}
	if c.FlushInterval <= 0 {
		c.FlushInterval = defaultFlushInterval
	}
	if c.ShutdownFlushTimeout <= 0 {
		c.ShutdownFlushTimeout = defaultShutdownFlushTimeout
	}
}
