package clickhouse

import "testing"

func TestUnit_OrderByKeys_ExtractsPrefix(t *testing.T) {
	t.Parallel()
	create := `CREATE TABLE ibex.evidence_spans (...) ENGINE = MergeTree ORDER BY (org_id, trace_id, span_id) TTL event_date + INTERVAL 90 DAY`
	got := orderByKeys(create)
	want := []string{"org_id", "trace_id", "span_id"}
	if !orderKeysMatch(got, want) {
		t.Fatalf("got=%v want=%v", got, want)
	}
}

func TestUnit_OrderByKeys_Missing(t *testing.T) {
	t.Parallel()
	if keys := orderByKeys("CREATE TABLE t (a Int)"); keys != nil {
		t.Fatalf("expected nil, got %v", keys)
	}
}
