package main

import (
	"strings"
	"testing"

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

func TestUnit_SetupTraceWriter_LogUsesRedactedDSN(t *testing.T) {
	raw := "clickhouse://default:s3cret@localhost:8123/ibex"
	got := ibexch.RedactedDSN(raw)
	if strings.Contains(got, "s3cret") {
		t.Fatalf("got %q", got)
	}
}
