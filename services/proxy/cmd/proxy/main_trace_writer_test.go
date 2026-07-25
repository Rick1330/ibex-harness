package main

import (
	"errors"
	"strings"
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestUnit_SetupTraceWriter_DisabledWhenDSNUnset(t *testing.T) {
	log := logger.Discard("proxy")
	reg := ibexmetrics.NewProxy("proxy")
	w, err := setupTraceWriter(config.Config{}, log, reg)
	if err != nil {
		t.Fatal(err)
	}
	if w != nil {
		t.Fatal("expected nil writer when DSN unset")
	}
}

func TestUnit_SetupTraceWriter_DisabledWhenDSNBlank(t *testing.T) {
	log := logger.Discard("proxy")
	reg := ibexmetrics.NewProxy("proxy")
	w, err := setupTraceWriter(config.Config{ClickHouseDSN: "   "}, log, reg)
	if err != nil {
		t.Fatal(err)
	}
	if w != nil {
		t.Fatal("expected nil writer when DSN blank")
	}
}

func TestUnit_SetupTraceWriter_PropagatesConfig(t *testing.T) {
	prev := newTraceWriter
	t.Cleanup(func() { newTraceWriter = prev })

	var got ibexch.Config
	stub := &ibexch.Writer{}
	newTraceWriter = func(cfg ibexch.Config) (*ibexch.Writer, error) {
		got = cfg
		return stub, nil
	}

	log := logger.Discard("proxy")
	reg := ibexmetrics.NewProxy("proxy-ch-setup")
	dsn := "clickhouse://default:s3cret@localhost:8123/ibex"
	w, err := setupTraceWriter(config.Config{
		ClickHouseDSN:       dsn,
		ClickHouseBatchSize: 42,
		ClickHouseFlushMS:   77,
	}, log, reg)
	if err != nil {
		t.Fatal(err)
	}
	if w != stub {
		t.Fatal("expected stub writer")
	}
	if got.DSN != dsn {
		t.Fatalf("dsn=%q", got.DSN)
	}
	if got.MaxBatchSize != 42 {
		t.Fatalf("batch=%d", got.MaxBatchSize)
	}
	if got.FlushInterval != 77*time.Millisecond {
		t.Fatalf("flush=%s", got.FlushInterval)
	}
	if got.Logger != log {
		t.Fatal("logger not wired")
	}
	if got.Metrics != reg {
		t.Fatal("metrics not wired")
	}
}

func TestUnit_SetupTraceWriter_WrapsStartError(t *testing.T) {
	prev := newTraceWriter
	t.Cleanup(func() { newTraceWriter = prev })
	newTraceWriter = func(ibexch.Config) (*ibexch.Writer, error) {
		return nil, errors.New("boom")
	}

	log := logger.Discard("proxy")
	reg := ibexmetrics.NewProxy("proxy")
	_, err := setupTraceWriter(config.Config{ClickHouseDSN: "clickhouse://x"}, log, reg)
	if err == nil || !strings.Contains(err.Error(), "clickhouse writer") {
		t.Fatalf("got %v", err)
	}
	if !strings.Contains(err.Error(), "boom") {
		t.Fatalf("want wrapped cause, got %v", err)
	}
}

func TestUnit_SetupTraceWriter_LogUsesRedactedDSN(t *testing.T) {
	raw := "clickhouse://default:s3cret@localhost:8123/ibex"
	got := ibexch.RedactedDSN(raw)
	if strings.Contains(got, "s3cret") {
		t.Fatalf("got %q", got)
	}
}
