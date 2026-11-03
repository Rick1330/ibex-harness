//go:build integration

package clickhousesink

import (
	"context"
	"os"
	"testing"
	"time"

	clickhouse "github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

type integrationFence struct{}

func (integrationFence) CheckFence(context.Context, uuid.UUID, evidenceoutbox.TombstoneFence) error {
	return nil
}

func TestIntegration_DeliverDedupesPerTenant(t *testing.T) {
	ctx, conn, sink, cleanup := openIntegrationSink(t)
	defer cleanup()

	fence := evidenceoutbox.TombstoneFence{ResourceType: "evidence_run", ResourceID: "run-1", ResourceVersion: 1}
	event := uuid.New()
	row := integrationRow(event)
	deliverIntegrationRows(t, ctx, integrationDelivery{sink: sink, row: row, fence: fence})
	assertIntegrationTenantRows(t, ctx, conn, event)
}

func openIntegrationSink(t *testing.T) (context.Context, driver.Conn, *Sink, func()) {
	t.Helper()
	dsn := os.Getenv("CLICKHOUSE_TEST_NATIVE_DSN")
	if dsn == "" {
		t.Skip("CLICKHOUSE_TEST_NATIVE_DSN is not set")
	}
	options, err := clickhouse.ParseDSN(dsn)
	if err != nil {
		t.Fatal(err)
	}
	conn, err := clickhouse.Open(options)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	if err := conn.Exec(ctx, "TRUNCATE TABLE ibex.evidence_events"); err != nil {
		cancel()
		_ = conn.Close()
		t.Fatal(err)
	}
	sink, err := New(conn, integrationFence{})
	if err != nil {
		cancel()
		_ = conn.Close()
		t.Fatal(err)
	}
	return ctx, conn, sink, func() {
		cancel()
		_ = sink.Close()
	}
}

func integrationRow(event uuid.UUID) evidenceoutbox.OutboxRow {
	return evidenceoutbox.OutboxRow{
		OrgID: uuid.New(), EventID: event, AggregateID: "req-1", AggregateSeq: 1,
		SchemaVersion: evidenceoutbox.SchemaVersion, EventType: evidenceoutbox.EventTypeRunCommitted,
		RedactionClass: evidenceoutbox.RedactionClassMetadata, Payload: []byte(`{"redaction_class":"metadata"}`),
	}
}

type integrationDelivery struct {
	sink  *Sink
	row   evidenceoutbox.OutboxRow
	fence evidenceoutbox.TombstoneFence
}

func deliverIntegrationRows(t *testing.T, ctx context.Context, delivery integrationDelivery) {
	t.Helper()
	if err := delivery.sink.DeliverWithTombstoneFence(ctx, delivery.row, delivery.fence); err != nil {
		t.Fatal(err)
	}
	if err := delivery.sink.DeliverWithTombstoneFence(ctx, delivery.row, delivery.fence); err != nil {
		t.Fatal(err)
	}
	delivery.row.OrgID = uuid.New()
	if err := delivery.sink.DeliverWithTombstoneFence(ctx, delivery.row, delivery.fence); err != nil {
		t.Fatal(err)
	}
}

func assertIntegrationTenantRows(t *testing.T, ctx context.Context, conn driver.Conn, event uuid.UUID) {
	t.Helper()
	var count uint64
	if err := conn.QueryRow(ctx, "SELECT count() FROM ibex.evidence_events WHERE event_id = ?", event).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 2 {
		t.Fatalf("event rows=%d want two tenant-scoped rows", count)
	}
}
