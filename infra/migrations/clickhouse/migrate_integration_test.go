//go:build integration

package clickhouse

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/ClickHouse/clickhouse-go"
)

// Test compose maps native 9000 → host 9003 (dev uses 9002).
const defaultTestMigrateDSN = "clickhouse://default:@localhost:9003?database=ibex&x-multi-statement=true&x-migrations-table-engine=MergeTree"

func testMigrateDSN() string {
	if dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_TEST_DSN")); dsn != "" {
		return normalizeMigrateDSN(dsn)
	}
	if dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_MIGRATE_DSN")); dsn != "" {
		return normalizeMigrateDSN(dsn)
	}
	return defaultTestMigrateDSN
}

func openTestCH(t *testing.T) *sql.DB {
	t.Helper()
	dsn := testMigrateDSN()
	u := strings.Replace(dsn, "clickhouse://", "tcp://", 1)
	db, err := sql.Open("clickhouse", u)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		t.Skipf("clickhouse not available: %v", err)
	}
	return db
}

func resetClickHouse(t *testing.T, db *sql.DB) {
	t.Helper()
	ctx := context.Background()
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS ibex.llm_traces`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS ibex.schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS default.schema_migrations`)
	_, _ = db.ExecContext(ctx, `DROP TABLE IF EXISTS schema_migrations`)
}

func TestMigrateUpIdempotent(t *testing.T) {
	dsn := testMigrateDSN()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("first up: %v", err)
	}
	if err := Up(dsn); err != nil {
		t.Fatalf("second up: %v", err)
	}
	v, dirty, err := Version(dsn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty {
		t.Fatal("expected clean")
	}
	if v != 1 {
		t.Fatalf("version=%d want 1", v)
	}
}

func TestLLMTracesSchemaAndTTL(t *testing.T) {
	dsn := testMigrateDSN()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	rows, err := db.QueryContext(ctx, `
		SELECT name FROM system.columns
		WHERE database = 'ibex' AND table = 'llm_traces'
		ORDER BY name`)
	if err != nil {
		t.Fatalf("columns: %v", err)
	}
	defer func() { _ = rows.Close() }()

	cols := map[string]struct{}{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatal(err)
		}
		cols[name] = struct{}{}
	}
	if err := rows.Err(); err != nil {
		t.Fatal(err)
	}

	required := []string{
		"request_id", "org_id", "agent_id", "session_id", "checkpoint_id",
		"model", "provider", "is_streaming",
		"input_tokens", "output_tokens", "total_tokens",
		"auth_latency_ms", "directive_latency_ms", "provider_ttfb_ms", "total_latency_ms",
		"status_code", "is_complete", "error_code",
		"requested_at", "completed_at", "event_date",
	}
	for _, c := range required {
		if _, ok := cols[c]; !ok {
			t.Errorf("missing column %s", c)
		}
	}
	for forbidden := range map[string]struct{}{
		"prompt": {}, "completion": {}, "prompt_text": {}, "completion_text": {},
		"messages": {}, "content": {},
	} {
		if _, ok := cols[forbidden]; ok {
			t.Errorf("content column must not exist: %s", forbidden)
		}
	}

	var createSQL string
	if err := db.QueryRowContext(ctx, `SHOW CREATE TABLE ibex.llm_traces`).Scan(&createSQL); err != nil {
		t.Fatalf("show create: %v", err)
	}
	if !strings.Contains(createSQL, "TTL") || !strings.Contains(createSQL, "90") {
		t.Fatalf("expected 90-day TTL in CREATE TABLE, got: %s", createSQL)
	}
	if !strings.Contains(createSQL, "ORDER BY") || !strings.Contains(createSQL, "org_id") {
		t.Fatalf("expected ORDER BY org_id in CREATE TABLE: %s", createSQL)
	}
}

func TestExplainUsesPrimaryKey(t *testing.T) {
	dsn := testMigrateDSN()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)
	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}

	ctx := context.Background()
	_, err := db.ExecContext(ctx, `
		INSERT INTO ibex.llm_traces (
			request_id, org_id, agent_id, session_id, checkpoint_id,
			model, provider, is_streaming,
			input_tokens, output_tokens, total_tokens,
			auth_latency_ms, directive_latency_ms, provider_ttfb_ms, total_latency_ms,
			status_code, is_complete, error_code,
			requested_at, completed_at
		) VALUES (
			'req-1', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222',
			NULL, NULL,
			'gpt-4o', 'openai', 0,
			10, 20, 30,
			1, 2, 100, 5,
			200, 1, '',
			now64(3), now64(3)
		)`)
	if err != nil {
		t.Fatalf("insert: %v", err)
	}

	explainRows, err := db.QueryContext(ctx, `
		EXPLAIN indexes = 1
		SELECT count()
		FROM ibex.llm_traces
		WHERE org_id = '11111111-1111-1111-1111-111111111111'
		  AND agent_id = '22222222-2222-2222-2222-222222222222'
		  AND requested_at >= now64(3) - INTERVAL 1 DAY`)
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	defer func() { _ = explainRows.Close() }()

	out := strings.ToLower(scanExplainText(t, explainRows))
	if !strings.Contains(out, "org_id") {
		t.Fatalf("EXPLAIN did not indicate org_id key usage: %s", out)
	}
}

func scanExplainText(t *testing.T, rows *sql.Rows) string {
	t.Helper()
	cols, err := rows.Columns()
	if err != nil {
		t.Fatal(err)
	}
	var b strings.Builder
	vals := make([]any, len(cols))
	ptrs := make([]any, len(cols))
	for i := range vals {
		ptrs[i] = &vals[i]
	}
	for rows.Next() {
		if err := rows.Scan(ptrs...); err != nil {
			t.Fatal(err)
		}
		for _, v := range vals {
			b.WriteString(stringifyScan(v))
			b.WriteByte(' ')
		}
	}
	if err := rows.Err(); err != nil {
		t.Fatal(err)
	}
	return b.String()
}

func stringifyScan(v any) string {
	switch t := v.(type) {
	case nil:
		return ""
	case []byte:
		return string(t)
	case string:
		return t
	default:
		return ""
	}
}

func TestMigrateDownUpRoundTrip(t *testing.T) {
	dsn := testMigrateDSN()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)

	if err := Up(dsn); err != nil {
		t.Fatalf("up: %v", err)
	}
	if err := Down(dsn); err != nil {
		t.Fatalf("down: %v", err)
	}
	var n uint64
	err := db.QueryRowContext(context.Background(), `
		SELECT count() FROM system.tables
		WHERE database = 'ibex' AND name = 'llm_traces'`).Scan(&n)
	if err != nil {
		t.Fatalf("count tables: %v", err)
	}
	if n != 0 {
		t.Fatalf("table still present after down, count=%d", n)
	}
	if err := Up(dsn); err != nil {
		t.Fatalf("up after down: %v", err)
	}
}
