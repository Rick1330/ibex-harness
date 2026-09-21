//go:build integration

package clickhouse

import (
	"context"
	"database/sql"
	"strings"
	"testing"
)

func TestIntegration_UsageFacts_NoTTLAndOrderBy(t *testing.T) {
	conn := testMigrateConn()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)
	if err := Up(conn); err != nil {
		t.Fatalf("up: %v", err)
	}
	assertTableCount(t, db, "usage_facts", 1)

	var createSQL string
	if err := db.QueryRowContext(context.Background(), `SHOW CREATE TABLE ibex.usage_facts`).Scan(&createSQL); err != nil {
		t.Fatalf("show create: %v", err)
	}
	upper := strings.ToUpper(createSQL)
	if strings.Contains(upper, " TTL ") {
		t.Fatalf("usage_facts must have no TTL, got: %s", createSQL)
	}
	if !strings.Contains(createSQL, "org_id") || !strings.Contains(createSQL, "ORDER BY") {
		t.Fatalf("expected ORDER BY org_id, got: %s", createSQL)
	}
	keys := orderByKeys(createSQL)
	want := []string{"org_id", "agent_id", "occurred_at"}
	if !orderKeysMatch(keys, want) {
		t.Fatalf("ORDER BY keys=%v want=%v", keys, want)
	}

	if err := Down(conn); err != nil {
		t.Fatalf("down: %v", err)
	}
	assertTableCount(t, db, "usage_facts", 0)
}

func insertSampleUsageFact(t *testing.T, db *sql.DB) {
	t.Helper()
	_, err := db.ExecContext(context.Background(), `
		INSERT INTO ibex.usage_facts (
			request_id, org_id, agent_id, provider, model,
			input_tokens, output_tokens, total_tokens,
			estimated_cost_cents, rate_card_version, completeness, occurred_at
		) VALUES (
			'test-req', generateUUIDv4(), generateUUIDv4(), 'openai', 'gpt-4o',
			10, 20, 30,
			5, '1', 'partial', now64(3)
		)`)
	if err != nil {
		t.Fatalf("insert usage_facts: %v", err)
	}
}
