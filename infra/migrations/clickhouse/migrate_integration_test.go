//go:build integration

package clickhouse

import (
	"context"
	"database/sql"
	"os"
	"strings"
	"testing"
	"time"

	// Registers the ClickHouse database/sql driver for integration tests.
	_ "github.com/ClickHouse/clickhouse-go"
)

// Test compose maps native 9000 → host 9003 (dev uses 9002).
const defaultTestMigrateDSN = "clickhouse://default:@localhost:9003?database=ibex&x-multi-statement=true&x-migrations-table-engine=MergeTree"

var requiredLLMTraceColumns = []string{
	"request_id", "org_id", "agent_id", "session_id", "checkpoint_id",
	"model", "provider", "is_streaming",
	"input_tokens", "output_tokens", "total_tokens",
	"auth_latency_ms", "directive_latency_ms", "provider_ttfb_ms", "total_latency_ms",
	"status_code", "is_complete", "error_code",
	"requested_at", "completed_at", "event_date",
}

func testMigrateConn() Conn {
	if dsn := strings.TrimSpace(os.Getenv("CLICKHOUSE_TEST_DSN")); dsn != "" {
		return ParseConn(dsn)
	}
	return ParseConn(defaultTestMigrateDSN)
}

func openTestCH(t *testing.T) *sql.DB {
	t.Helper()
	dsn := testMigrateConn().String()
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
	drops := []string{
		`DROP TABLE IF EXISTS ibex.mcp_tool_calls`,
		`DROP TABLE IF EXISTS ibex.llm_traces`,
		`DROP TABLE IF EXISTS ibex.schema_migrations`,
		`DROP TABLE IF EXISTS default.schema_migrations`,
		`DROP TABLE IF EXISTS schema_migrations`,
	}
	for _, q := range drops {
		if _, err := db.ExecContext(ctx, q); err != nil {
			t.Fatalf("reset %q: %v", q, err)
		}
	}
}

func TestIntegration_Migrate_UpIsIdempotent(t *testing.T) {
	conn := testMigrateConn()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)

	if err := Up(conn); err != nil {
		t.Fatalf("first up: %v", err)
	}
	if err := Up(conn); err != nil {
		t.Fatalf("second up: %v", err)
	}
	v, dirty, err := Version(conn)
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if dirty || v != 2 {
		t.Fatalf("version=%d dirty=%v want 2/clean", v, dirty)
	}
}

func TestIntegration_Migrate_SchemaAndTTL(t *testing.T) {
	conn := testMigrateConn()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)
	if err := Up(conn); err != nil {
		t.Fatalf("up: %v", err)
	}
	assertRequiredColumns(t, db)
	assertNoContentColumns(t, db)
	assertCreateTableDDL(t, db)
	assertMCPToolCallsTable(t, db)
}

func assertMCPToolCallsTable(t *testing.T, db *sql.DB) {
	t.Helper()
	assertTableCount(t, db, "mcp_tool_calls", 1)
	rows, err := db.QueryContext(context.Background(), `
		SELECT name FROM system.columns
		WHERE database = 'ibex' AND table = 'mcp_tool_calls'`)
	if err != nil {
		t.Fatalf("mcp columns: %v", err)
	}
	defer func() { _ = rows.Close() }()
	got := map[string]struct{}{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			t.Fatal(err)
		}
		got[name] = struct{}{}
	}
	if err := rows.Err(); err != nil {
		t.Fatal(err)
	}
	for _, col := range []string{
		"request_id", "org_id", "agent_id", "tool_name",
		"latency_ms", "success", "error_code", "requested_at", "event_date",
	} {
		if _, ok := got[col]; !ok {
			t.Errorf("mcp_tool_calls missing column %s", col)
		}
	}
	for _, forbidden := range []string{"content", "query", "arguments", "payload"} {
		if _, ok := got[forbidden]; ok {
			t.Errorf("mcp_tool_calls must not store content column %s", forbidden)
		}
	}
}

func assertRequiredColumns(t *testing.T, db *sql.DB) {
	t.Helper()
	cols := loadColumnNames(t, db)
	assertMissingColumns(t, cols)
	assertExtraColumns(t, cols)
}

func assertMissingColumns(t *testing.T, cols map[string]struct{}) {
	t.Helper()
	for _, c := range requiredLLMTraceColumns {
		if _, ok := cols[c]; !ok {
			t.Errorf("missing column %s", c)
		}
	}
}

func assertExtraColumns(t *testing.T, cols map[string]struct{}) {
	t.Helper()
	required := requiredColumnSet()
	for name := range cols {
		if !required[name] {
			t.Errorf("unexpected column %s", name)
		}
	}
}

func requiredColumnSet() map[string]bool {
	out := make(map[string]bool, len(requiredLLMTraceColumns))
	for _, c := range requiredLLMTraceColumns {
		out[c] = true
	}
	return out
}

func assertNoContentColumns(t *testing.T, db *sql.DB) {
	t.Helper()
	cols := loadColumnNames(t, db)
	for _, forbidden := range []string{"prompt", "completion", "prompt_text", "completion_text", "messages", "content", "prompt_payload"} {
		if _, ok := cols[forbidden]; ok {
			t.Errorf("content column must not exist: %s", forbidden)
		}
	}
}

func assertCreateTableDDL(t *testing.T, db *sql.DB) {
	t.Helper()
	var createSQL string
	if err := db.QueryRowContext(context.Background(), `SHOW CREATE TABLE ibex.llm_traces`).Scan(&createSQL); err != nil {
		t.Fatalf("show create: %v", err)
	}
	if !strings.Contains(createSQL, "event_date + toIntervalDay(90)") &&
		!strings.Contains(createSQL, "event_date + INTERVAL 90 DAY") {
		t.Fatalf("expected event_date 90-day TTL, got: %s", createSQL)
	}
	if !strings.Contains(createSQL, "org_id") || !strings.Contains(createSQL, "ORDER BY") {
		t.Fatalf("expected ORDER BY org_id, got: %s", createSQL)
	}
}

func assertTableCount(t *testing.T, db *sql.DB, name string, want uint64) {
	t.Helper()
	allowed := map[string]struct{}{
		"mcp_tool_calls": {},
		"llm_traces":     {},
	}
	if _, ok := allowed[name]; !ok {
		t.Fatalf("unknown table %s", name)
	}
	var n uint64
	q := "SELECT count() FROM system.tables WHERE database = ? AND name = ?"
	if err := db.QueryRowContext(context.Background(), q, "ibex", name).Scan(&n); err != nil {
		t.Fatalf("count tables %s: %v", name, err)
	}
	if n != want {
		t.Fatalf("table %s count=%d want=%d", name, n, want)
	}
}

func loadColumnNames(t *testing.T, db *sql.DB) map[string]struct{} {
	t.Helper()
	rows, err := db.QueryContext(context.Background(), `
		SELECT name FROM system.columns
		WHERE database = 'ibex' AND table = 'llm_traces'`)
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
	return cols
}

func TestIntegration_Migrate_ExplainUsesPrimaryKey(t *testing.T) {
	conn := testMigrateConn()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)
	if err := Up(conn); err != nil {
		t.Fatalf("up: %v", err)
	}
	insertSampleTrace(t, db)
	out := strings.ToLower(explainOrgAgentQuery(t, db))
	if !strings.Contains(out, "org_id") {
		t.Fatalf("EXPLAIN did not indicate org_id key usage: %s", out)
	}
}

func insertSampleTrace(t *testing.T, db *sql.DB) {
	t.Helper()
	_, err := db.ExecContext(context.Background(), `
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
}

func explainOrgAgentQuery(t *testing.T, db *sql.DB) string {
	t.Helper()
	rows, err := db.QueryContext(context.Background(), `
		EXPLAIN indexes = 1
		SELECT count()
		FROM ibex.llm_traces
		WHERE org_id = '11111111-1111-1111-1111-111111111111'
		  AND agent_id = '22222222-2222-2222-2222-222222222222'
		  AND requested_at >= now64(3) - INTERVAL 1 DAY`)
	if err != nil {
		t.Fatalf("explain: %v", err)
	}
	defer func() { _ = rows.Close() }()
	return scanExplainText(t, rows)
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

func TestIntegration_Migrate_DownUpRoundTrip(t *testing.T) {
	conn := testMigrateConn()
	db := openTestCH(t)
	defer db.Close()
	resetClickHouse(t, db)

	if err := Up(conn); err != nil {
		t.Fatalf("up: %v", err)
	}
	if err := Down(conn); err != nil {
		t.Fatalf("down mcp_tool_calls: %v", err)
	}
	assertTableCount(t, db, "mcp_tool_calls", 0)
	assertTableCount(t, db, "llm_traces", 1)
	if err := Down(conn); err != nil {
		t.Fatalf("down llm_traces: %v", err)
	}
	assertTableCount(t, db, "llm_traces", 0)
	if err := Up(conn); err != nil {
		t.Fatalf("up after down: %v", err)
	}
}
