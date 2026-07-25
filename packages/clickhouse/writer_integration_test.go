//go:build integration

package clickhouse

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	ch "github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/google/uuid"
)

const defaultTestAppDSN = "clickhouse://default:@localhost:8124/ibex"

func testAppDSN() string {
	if dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_TEST_DSN")); dsn != "" {
		return dsn
	}
	return defaultTestAppDSN
}

func TestIntegration_Writer_InsertAndSelect(t *testing.T) {
	dsn := testAppDSN()
	w, err := NewWriter(Config{
		DSN:           dsn,
		MaxBatchSize:  10,
		FlushInterval: time.Hour,
	})
	if err != nil {
		t.Skipf("clickhouse not available: %v", err)
	}
	defer func() { _ = w.Close() }()

	conn := openAssertConn(t, dsn)
	defer func() { _ = conn.Close() }()
	resetTraces(t, conn)

	rec := sampleRecord("integ-req-1")
	sid := uuid.MustParse("33333333-3333-3333-3333-333333333333")
	rec.SessionID = &sid
	if err := w.Write(rec); err != nil {
		t.Fatal(err)
	}
	if err := w.Flush(context.Background()); err != nil {
		t.Fatalf("flush: %v", err)
	}

	var n uint64
	err = conn.QueryRow(context.Background(), `
		SELECT count() FROM ibex.llm_traces WHERE request_id = {id:String}`,
		rec.RequestID).Scan(&n)
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("count=%d", n)
	}
	assertNoContentColumns(t, conn)
}

func openAssertConn(t *testing.T, dsn string) driver.Conn {
	t.Helper()
	opts, err := parseOptions(dsn)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	conn, err := ch.Open(opts)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := conn.Ping(ctx); err != nil {
		_ = conn.Close()
		t.Skipf("clickhouse ping: %v", err)
	}
	return conn
}

func resetTraces(t *testing.T, conn driver.Conn) {
	t.Helper()
	if err := conn.Exec(context.Background(), `TRUNCATE TABLE IF EXISTS ibex.llm_traces`); err != nil {
		t.Fatalf("truncate: %v", err)
	}
}

func assertNoContentColumns(t *testing.T, conn driver.Conn) {
	t.Helper()
	rows, err := conn.Query(context.Background(), `
		SELECT name FROM system.columns
		WHERE database = 'ibex' AND table = 'llm_traces'`)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	cols := map[string]struct{}{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatal(err)
		}
		cols[name] = struct{}{}
	}
	for _, bad := range []string{"prompt", "completion", "content", "messages"} {
		if _, ok := cols[bad]; ok {
			t.Errorf("content column present: %s", bad)
		}
	}
}
