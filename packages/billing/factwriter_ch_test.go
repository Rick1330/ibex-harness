package billing

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/column"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
)

type fakeBatch struct {
	rows    [][]any
	appendE error
	sendE   error
	sent    bool
}

func (b *fakeBatch) Append(v ...any) error {
	if b.appendE != nil {
		return b.appendE
	}
	cp := append([]any(nil), v...)
	b.rows = append(b.rows, cp)
	return nil
}

func (b *fakeBatch) Abort() error                  { return nil }
func (b *fakeBatch) Flush() error                  { return nil }
func (b *fakeBatch) Send() error                   { b.sent = true; return b.sendE }
func (b *fakeBatch) IsSent() bool                  { return b.sent }
func (b *fakeBatch) Rows() int                     { return len(b.rows) }
func (b *fakeBatch) Columns() []column.Interface   { return nil }
func (b *fakeBatch) Column(int) driver.BatchColumn { return nil }
func (b *fakeBatch) AppendStruct(any) error        { return nil }
func (b *fakeBatch) Close() error                  { return nil }

type fakeConn struct {
	batch    *fakeBatch
	prepareE error
	pingE    error
	closed   bool
}

func (c *fakeConn) PrepareBatch(_ context.Context, _ string, _ ...driver.PrepareBatchOption) (driver.Batch, error) {
	if c.prepareE != nil {
		return nil, c.prepareE
	}
	if c.batch == nil {
		c.batch = &fakeBatch{}
	}
	return c.batch, nil
}

func (c *fakeConn) Ping(context.Context) error { return c.pingE }

func (c *fakeConn) Close() error {
	c.closed = true
	return nil
}

func TestChUsageFactInserter_InsertUsageFacts_AppendsAndSends(t *testing.T) {
	t.Parallel()
	batch := &fakeBatch{}
	conn := &fakeConn{batch: batch}
	ins := &chUsageFactInserter{conn: conn}

	orig, fb := "gpt-4o", "claude-sonnet"
	fact := validUsageFact()
	fact.Completeness = ""
	fact.OriginalModel = &orig
	fact.FallbackModel = &fb
	fact.FallbackReason = "circuit_open"

	if err := ins.InsertUsageFacts(context.Background(), []UsageFact{fact}); err != nil {
		t.Fatal(err)
	}
	if !batch.sent {
		t.Fatal("expected Send to be called")
	}
	if len(batch.rows) != 1 {
		t.Fatalf("rows=%d", len(batch.rows))
	}
	row := batch.rows[0]
	if got, ok := row[13].(string); !ok || got != "partial" {
		t.Fatalf("completeness=%v want partial", row[13])
	}
	if row[5] != &orig {
		t.Fatalf("original_model=%v", row[5])
	}
	if row[6] != &fb {
		t.Fatalf("fallback_model=%v", row[6])
	}
}

func TestChUsageFactInserter_InsertUsageFacts_PrepareBatchError(t *testing.T) {
	t.Parallel()
	ins := &chUsageFactInserter{conn: &fakeConn{prepareE: errors.New("prep")}}
	err := ins.InsertUsageFacts(context.Background(), []UsageFact{validUsageFact()})
	if err == nil || !strings.Contains(err.Error(), "prepare") {
		t.Fatalf("got %v", err)
	}
}

func TestChUsageFactInserter_InsertUsageFacts_AppendError(t *testing.T) {
	t.Parallel()
	ins := &chUsageFactInserter{conn: &fakeConn{batch: &fakeBatch{appendE: errors.New("append failed")}}}
	err := ins.InsertUsageFacts(context.Background(), []UsageFact{validUsageFact()})
	if err == nil || !strings.Contains(err.Error(), "append") {
		t.Fatalf("got %v", err)
	}
}

func TestChUsageFactInserter_InsertUsageFacts_EmptyRowsNoop(t *testing.T) {
	t.Parallel()
	conn := &fakeConn{}
	ins := &chUsageFactInserter{conn: conn}
	if err := ins.InsertUsageFacts(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
	if conn.batch != nil {
		t.Fatal("empty rows must not prepare a batch")
	}
}

func TestChUsageFactInserter_Close(t *testing.T) {
	t.Parallel()
	conn := &fakeConn{}
	ins := &chUsageFactInserter{conn: conn}
	if err := ins.Close(); err != nil {
		t.Fatal(err)
	}
	if !conn.closed {
		t.Fatal("expected conn closed")
	}
}

func TestOpenUsageFactInserter_PingFailureCloses(t *testing.T) {
	prev := openCHConn
	t.Cleanup(func() { openCHConn = prev })
	fc := &fakeConn{pingE: errors.New("down")}
	openCHConn = func(*clickhouse.Options) (usageFactConn, error) { return fc, nil }

	_, err := openUsageFactInserter("clickhouse://default:@localhost:8123/ibex")
	if err == nil {
		t.Fatal("expected ping error")
	}
	if !strings.Contains(err.Error(), "ping") {
		t.Fatalf("got %v", err)
	}
	if !fc.closed {
		t.Fatal("conn should close after ping failure")
	}
}

func TestOpenUsageFactInserter_OpenFailure(t *testing.T) {
	prev := openCHConn
	t.Cleanup(func() { openCHConn = prev })
	openCHConn = func(*clickhouse.Options) (usageFactConn, error) {
		return nil, errors.New("dial")
	}
	_, err := openUsageFactInserter("clickhouse://default:@localhost:8123/ibex")
	if err == nil || !strings.Contains(err.Error(), "open") {
		t.Fatalf("got %v", err)
	}
}

func TestOpenUsageFactInserter_ParseDSNError(t *testing.T) {
	t.Parallel()
	_, err := openUsageFactInserter("")
	if err == nil || !strings.Contains(err.Error(), "parse dsn") {
		t.Fatalf("got %v", err)
	}
}
