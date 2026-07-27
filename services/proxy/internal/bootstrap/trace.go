package bootstrap

import (
	"context"
	"fmt"
	"strings"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"

	// Register the lib/pq "postgres" driver used by sql.Open for directives + sessions.
	_ "github.com/lib/pq"
)

var newTraceWriter = ibexch.NewWriter

// optionalTraceWriter starts the ClickHouse writer or returns nil (fail-open).
func optionalTraceWriter(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
) *ibexch.Writer {
	w, err := setupTraceWriter(cfg, log, reg)
	if err != nil {
		log.WarnCtx(context.Background(), "clickhouse writer disabled; continuing without traces",
			"reason", "writer_start_failed")
		return nil
	}
	return w
}

func setupTraceWriter(
	cfg config.Config,
	log *logger.Logger,
	reg *ibexmetrics.ProxyRegistry,
) (*ibexch.Writer, error) {
	dsn := strings.TrimSpace(cfg.ClickHouseDSN)
	if dsn == "" {
		log.InfoCtx(context.Background(), "CLICKHOUSE_DSN unset; trace writer disabled")
		return nil, nil
	}
	w, err := newTraceWriter(ibexch.Config{
		DSN:           dsn,
		MaxBatchSize:  cfg.ClickHouseBatchSize,
		FlushInterval: time.Duration(cfg.ClickHouseFlushMS) * time.Millisecond,
		Logger:        log,
		Metrics:       reg,
	})
	if err != nil {
		return nil, fmt.Errorf("clickhouse writer: %w", err)
	}
	log.InfoCtx(context.Background(), "clickhouse trace writer started",
		"dsn", ibexch.RedactedDSN(dsn),
		"batch_size", cfg.ClickHouseBatchSize,
		"flush_ms", cfg.ClickHouseFlushMS,
	)
	return w, nil
}
