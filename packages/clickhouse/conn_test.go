package clickhouse

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/column"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/google/uuid"
)

type fakeBatch struct {
	rows    [][]any
	appendE error
	sendE   error
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
func (b *fakeBatch) Send() error                   { return b.sendE }
func (b *fakeBatch) IsSent() bool                  { return false }
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
	pingCtx  context.Context
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

func (c *fakeConn) Ping(ctx context.Context) error {
	c.pingCtx = ctx
	return c.pingE
}

func (c *fakeConn) Close() error {
	c.closed = true
	return nil
}

func TestUnit_CHInserter_InsertTraces(t *testing.T) {
	t.Parallel()
	conn := &fakeConn{batch: &fakeBatch{}}
	ins := newCHInserter(conn)
	rec := sampleRecord("ins-1")
	sid := uuid.MustParse("33333333-3333-3333-3333-333333333333")
	rec.SessionID = &sid

	if err := ins.InsertTraces(context.Background(), []TraceRecord{rec}); err != nil {
		t.Fatal(err)
	}
	if len(conn.batch.rows) != 1 {
		t.Fatalf("rows=%d", len(conn.batch.rows))
	}
	row := conn.batch.rows[0]
	if got := row[0]; got != "ins-1" {
		t.Fatalf("request_id=%v", got)
	}
	if row[3] != sid {
		t.Fatalf("session_id=%v", row[3])
	}
	if row[4] != nil {
		t.Fatalf("checkpoint_id want nil, got %v", row[4])
	}
}

func TestUnit_CHInserter_EmptyNoop(t *testing.T) {
	t.Parallel()
	ins := newCHInserter(&fakeConn{})
	if err := ins.InsertTraces(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_CHInserter_PrepareError(t *testing.T) {
	t.Parallel()
	ins := newCHInserter(&fakeConn{prepareE: errors.New("prep")})
	err := ins.InsertTraces(context.Background(), []TraceRecord{sampleRecord("x")})
	if err == nil || !strings.Contains(err.Error(), "prepare") {
		t.Fatalf("got %v", err)
	}
}

func TestUnit_CHInserter_AppendError(t *testing.T) {
	t.Parallel()
	ins := newCHInserter(&fakeConn{batch: &fakeBatch{appendE: errors.New("append")}})
	err := ins.InsertTraces(context.Background(), []TraceRecord{sampleRecord("x")})
	if err == nil || !strings.Contains(err.Error(), "append") {
		t.Fatalf("got %v", err)
	}
}

func TestUnit_CHInserter_SendError(t *testing.T) {
	t.Parallel()
	ins := newCHInserter(&fakeConn{batch: &fakeBatch{sendE: errors.New("send")}})
	err := ins.InsertTraces(context.Background(), []TraceRecord{sampleRecord("x")})
	if err == nil || !strings.Contains(err.Error(), "send") {
		t.Fatalf("got %v", err)
	}
}

func TestUnit_OpenInserter_ParseError(t *testing.T) {
	t.Parallel()
	if _, err := OpenInserter(""); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_OpenInserter_PingFailureCloses(t *testing.T) {
	// Mutates package-level openConn; must not run in parallel with other openConn tests.
	prev := openConn
	t.Cleanup(func() { openConn = prev })
	fc := &fakeConn{pingE: errors.New("down")}
	openConn = func(*clickhouse.Options) (batchConn, error) { return fc, nil }

	_, err := OpenInserter("clickhouse://default:@localhost:8123/ibex")
	if err == nil {
		t.Fatal("expected ping error")
	}
	if !strings.Contains(err.Error(), "ping") {
		t.Fatalf("got %v", err)
	}
	if !fc.closed {
		t.Fatal("conn should close after ping failure")
	}
	if fc.pingCtx == nil {
		t.Fatal("ping should receive a context")
	}
	deadline, ok := fc.pingCtx.Deadline()
	if !ok || time.Until(deadline) > pingTimeout {
		t.Fatalf("ping context missing timeout deadline: ok=%v deadline=%v", ok, deadline)
	}
}

func TestUnit_OpenInserter_OpenFailure(t *testing.T) {
	prev := openConn
	t.Cleanup(func() { openConn = prev })
	openConn = func(*clickhouse.Options) (batchConn, error) {
		return nil, errors.New("dial")
	}
	_, err := OpenInserter("clickhouse://default:@localhost:8123/ibex")
	if err == nil || !strings.Contains(err.Error(), "open") {
		t.Fatalf("got %v", err)
	}
}

func TestUnit_OpenInserter_Success(t *testing.T) {
	prev := openConn
	t.Cleanup(func() { openConn = prev })
	openConn = func(*clickhouse.Options) (batchConn, error) {
		return &fakeConn{}, nil
	}
	ins, err := OpenInserter("clickhouse://default:@localhost:8123/ibex")
	if err != nil {
		t.Fatal(err)
	}
	if err := ins.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_NullableUUID(t *testing.T) {
	t.Parallel()
	if nullableUUID(nil) != nil {
		t.Fatal("nil")
	}
	id := uuid.MustParse("33333333-3333-3333-3333-333333333333")
	if nullableUUID(&id) != id {
		t.Fatal("value")
	}
}
