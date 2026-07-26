package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/google/uuid"
)

func TestUnit_SetupTraceWriter_DisabledWhenDSNEmpty(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		dsn  string
	}{
		{name: "unset", dsn: ""},
		{name: "blank", dsn: "   "},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			log := logger.Discard("proxy")
			reg := ibexmetrics.NewProxy("proxy-" + tc.name)

			w, err := setupTraceWriter(config.Config{ClickHouseDSN: tc.dsn}, log, reg)

			if err != nil {
				t.Fatal(err)
			}
			if w != nil {
				t.Fatal("expected nil writer when DSN empty")
			}
		})
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
	wantErr := errors.New("boom")
	newTraceWriter = func(ibexch.Config) (*ibexch.Writer, error) {
		return nil, wantErr
	}

	log := logger.Discard("proxy")
	reg := ibexmetrics.NewProxy("proxy")
	_, err := setupTraceWriter(config.Config{ClickHouseDSN: "clickhouse://x"}, log, reg)
	if err == nil || !strings.Contains(err.Error(), "clickhouse writer") {
		t.Fatalf("got %v", err)
	}
	if !errors.Is(err, wantErr) {
		t.Fatalf("want wrapped cause, got %v", err)
	}
}

func TestUnit_SetupTraceWriter_LogUsesRedactedDSN(t *testing.T) {
	prev := newTraceWriter
	t.Cleanup(func() { newTraceWriter = prev })
	newTraceWriter = func(ibexch.Config) (*ibexch.Writer, error) {
		return &ibexch.Writer{}, nil
	}

	var buf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "proxy",
		Level:   slog.LevelInfo,
		Writer:  &buf,
	})
	if err != nil {
		t.Fatal(err)
	}
	reg := ibexmetrics.NewProxy("proxy-ch-redact")
	secret := "s3cret-password"
	dsn := "clickhouse://default:" + secret + "@localhost:8123/ibex"

	_, err = setupTraceWriter(config.Config{ClickHouseDSN: dsn}, log, reg)
	if err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, "clickhouse trace writer started") {
		t.Fatalf("missing startup log: %q", out)
	}
	if strings.Contains(out, secret) {
		t.Fatalf("password leaked in log: %q", out)
	}
}

func TestUnit_OptionalTraceWriter_FailOpenOnStartError(t *testing.T) {
	prev := newTraceWriter
	t.Cleanup(func() { newTraceWriter = prev })
	newTraceWriter = func(ibexch.Config) (*ibexch.Writer, error) {
		return nil, errors.New("boom")
	}

	var buf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "proxy",
		Level:   slog.LevelWarn,
		Writer:  &buf,
	})
	if err != nil {
		t.Fatal(err)
	}
	w := optionalTraceWriter(config.Config{ClickHouseDSN: "clickhouse://x"}, log, ibexmetrics.NewProxy("proxy"))
	if w != nil {
		t.Fatal("expected nil writer on start failure")
	}
	if !strings.Contains(buf.String(), "clickhouse writer disabled") {
		t.Fatalf("missing fail-open log: %q", buf.String())
	}
	if !strings.Contains(buf.String(), "writer_start_failed") {
		t.Fatalf("missing sanitized reason: %q", buf.String())
	}
}

func TestUnit_AssignTraceWriter_SkipsNilConcrete(t *testing.T) {
	t.Parallel()
	deps := proxyhttp.RouterDeps{}
	assignTraceWriter(&deps, nil)
	if deps.TraceWriter != nil {
		t.Fatal("nil *Writer must not be boxed into TraceWriter")
	}
	w := &ibexch.Writer{}
	assignTraceWriter(&deps, w)
	if deps.TraceWriter != w {
		t.Fatal("non-nil writer not assigned")
	}
}

func TestUnit_OptionalTraceWriter_FailOpenOmitsSensitiveError(t *testing.T) {
	prev := newTraceWriter
	t.Cleanup(func() { newTraceWriter = prev })
	secret := "clickhouse://default:super-secret-pass@localhost:8123/ibex"
	newTraceWriter = func(ibexch.Config) (*ibexch.Writer, error) {
		return nil, fmt.Errorf("dial failed for %s", secret)
	}

	var buf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "proxy",
		Level:   slog.LevelWarn,
		Writer:  &buf,
	})
	if err != nil {
		t.Fatal(err)
	}
	w := optionalTraceWriter(config.Config{ClickHouseDSN: secret}, log, ibexmetrics.NewProxy("proxy"))
	if w != nil {
		t.Fatal("expected nil writer on start failure")
	}
	out := buf.String()
	if !strings.Contains(out, "writer_start_failed") {
		t.Fatalf("missing sanitized reason: %q", out)
	}
	if strings.Contains(out, "super-secret-pass") || strings.Contains(out, secret) {
		t.Fatalf("sensitive error leaked into log: %q", out)
	}
}

func TestUnit_FinishProxyCore_PassesTraceWriter(t *testing.T) {
	w := &ibexch.Writer{}
	core := finishProxyCore(proxyCoreParts{
		assembled: assembledProxyCore{traceWriter: w},
	})
	if core.traceWriter != w {
		t.Fatal("traceWriter not wired from assembled core")
	}
}

// sampleTrace for shutdown drain assertions (valid TraceRecord).
func sampleTrace(id string) ibexch.TraceRecord {
	now := time.Now().UTC()
	return ibexch.TraceRecord{
		RequestID:   id,
		OrgID:       uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		AgentID:     uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		Model:       "gpt-4o",
		Provider:    "openai",
		StatusCode:  200,
		IsComplete:  true,
		RequestedAt: now,
		CompletedAt: now,
	}
}

type recordingTraceInserter struct {
	mu     sync.Mutex
	rows   []ibexch.TraceRecord
	closed atomic.Bool
}

func (r *recordingTraceInserter) InsertTraces(_ context.Context, rows []ibexch.TraceRecord) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.rows = append(r.rows, rows...)
	return nil
}

func (r *recordingTraceInserter) Close() error {
	r.closed.Store(true)
	return nil
}

func (r *recordingTraceInserter) rowCount() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.rows)
}
