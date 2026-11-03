package clickhousesink

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

type fakeRow struct {
	count uint64
	err   error
}

func (r fakeRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	*dest[0].(*uint64) = r.count
	return nil
}

func (r fakeRow) Err() error { return r.err }

func (r fakeRow) ScanStruct(any) error { return r.err }

type fakeConn struct {
	count uint64
	err   error
	exec  int
	query string
	args  []any
}

func (c *fakeConn) QueryRow(_ context.Context, query string, args ...any) driver.Row {
	c.query, c.args = query, args
	return fakeRow{count: c.count, err: c.err}
}

func (c *fakeConn) Exec(_ context.Context, _ string, args ...any) error {
	c.exec++
	c.args = args
	return c.err
}

func (c *fakeConn) Ping(context.Context) error { return c.err }

func (c *fakeConn) Close() error { return nil }

type fakeFence struct{ err error }

func (f fakeFence) CheckFence(context.Context, uuid.UUID, evidenceoutbox.TombstoneFence) error {
	return f.err
}

func TestNewRequiresAuthoritativeFenceChecker(t *testing.T) {
	if _, err := New(&fakeConn{}, nil); err == nil {
		t.Fatal("expected fence checker requirement")
	}
}

func TestPingReportsConnectionError(t *testing.T) {
	sink, err := New(&fakeConn{}, fakeFence{})
	if err != nil {
		t.Fatal(err)
	}
	if err := sink.Ping(context.Background()); err != nil {
		t.Fatalf("healthy ping: %v", err)
	}
	down, err := New(&fakeConn{err: errors.New("clickhouse unavailable")}, fakeFence{})
	if err != nil {
		t.Fatal(err)
	}
	if err := down.Ping(context.Background()); err == nil {
		t.Fatal("expected ping error")
	}
}

func TestDeliverDeduplicatesWithinTenant(t *testing.T) {
	conn := &fakeConn{count: 1}
	sink, err := New(conn, fakeFence{})
	if err != nil {
		t.Fatal(err)
	}
	row := testRow()
	if err := sink.DeliverWithTombstoneFence(context.Background(), row, testFence()); err != nil {
		t.Fatal(err)
	}
	if conn.exec != 0 {
		t.Fatalf("duplicate was inserted: %d", conn.exec)
	}
	if !strings.Contains(conn.query, "org_id = ?") {
		t.Fatalf("dedupe query lost tenant predicate: %s", conn.query)
	}
}

func TestDeliverChecksFenceBeforeProjection(t *testing.T) {
	conn := &fakeConn{}
	sink, err := New(conn, fakeFence{err: errors.New("authority unavailable")})
	if err != nil {
		t.Fatal(err)
	}
	if err := sink.DeliverWithTombstoneFence(context.Background(), testRow(), testFence()); err == nil {
		t.Fatal("expected authoritative fence failure")
	}
	if conn.exec != 0 {
		t.Fatal("projection ran after fence failure")
	}
}

func TestDeliverInsertsValidatedProjection(t *testing.T) {
	conn := &fakeConn{}
	sink, err := New(conn, fakeFence{})
	if err != nil {
		t.Fatal(err)
	}
	if err := sink.DeliverWithTombstoneFence(context.Background(), testRow(), testFence()); err != nil {
		t.Fatal(err)
	}
	if conn.exec != 1 {
		t.Fatalf("exec=%d want 1", conn.exec)
	}
}

func TestDeliverRejectsInvalidFence(t *testing.T) {
	conn := &fakeConn{}
	sink, err := New(conn, fakeFence{})
	if err != nil {
		t.Fatal(err)
	}
	if err := sink.DeliverWithTombstoneFence(context.Background(), testRow(), evidenceoutbox.TombstoneFence{}); err == nil {
		t.Fatal("expected invalid fence")
	}
}

func testRow() evidenceoutbox.OutboxRow {
	return evidenceoutbox.OutboxRow{
		OrgID: uuid.New(), EventID: uuid.New(), AggregateID: "request-1", AggregateSeq: 1,
		SchemaVersion: evidenceoutbox.SchemaVersion, EventType: evidenceoutbox.EventTypeRunCommitted,
		Payload: []byte(`{"redaction_class":"metadata"}`),
	}
}

func testFence() evidenceoutbox.TombstoneFence {
	return evidenceoutbox.TombstoneFence{ResourceType: "evidence_run", ResourceID: "run-1", ResourceVersion: 1}
}
