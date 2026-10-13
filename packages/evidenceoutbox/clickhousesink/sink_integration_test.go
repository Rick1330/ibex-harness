//go:build integration

package clickhousesink

import (
	"context"
	"os"
	"testing"
	"time"

	clickhouse "github.com/ClickHouse/clickhouse-go/v2"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
	"github.com/google/uuid"
)

type integrationFence struct{}

func (integrationFence) CheckFence(context.Context, uuid.UUID, evidenceoutbox.TombstoneFence) error {
	return nil
}

func TestIntegration_DeliverDedupesPerTenant(t *testing.T) {
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
	defer conn.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := conn.Exec(ctx, "TRUNCATE TABLE ibex.evidence_events"); err != nil {
		t.Fatal(err)
	}
	sink, err := New(conn, integrationFence{})
	if err != nil {
		t.Fatal(err)
	}
	defer sink.Close()
	fence := evidenceoutbox.TombstoneFence{ResourceType: "evidence_run", ResourceID: "run-1", ResourceVersion: 1}
	event := uuid.New()
	row := evidenceoutbox.OutboxRow{
		OrgID: uuid.New(), EventID: event, AggregateID: "req-1", AggregateSeq: 1,
		SchemaVersion: evidenceoutbox.SchemaVersion, EventType: evidenceoutbox.EventTypeRunCommitted,
		RedactionClass: evidenceoutbox.RedactionClassMetadata, Payload: []byte(`{"redaction_class":"metadata"}`),
	}
	if err := sink.DeliverWithTombstoneFence(ctx, row, fence); err != nil {
		t.Fatal(err)
	}
	if err := sink.DeliverWithTombstoneFence(ctx, row, fence); err != nil {
		t.Fatal(err)
	}
	row.OrgID = uuid.New()
	if err := sink.DeliverWithTombstoneFence(ctx, row, fence); err != nil {
		t.Fatal(err)
	}
	var count uint64
	if err := conn.QueryRow(ctx, "SELECT count() FROM ibex.evidence_events WHERE event_id = ?", event).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 2 {
		t.Fatalf("event rows=%d want two tenant-scoped rows", count)
	}
}
