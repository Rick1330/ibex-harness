package usagequery

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

const goldenOrgTimeAggregate = "org_time_aggregate.sql"

func TestGoldenSQL_OrgTimeAggregate(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := start.Add(24 * time.Hour)
	r, err := RenderSQL(Query{
		Shape: ShapeOrgTimeAggregate, OrgID: org, Start: start, End: end, Limit: 100,
	}, BudgetLimits{MaxRows: 10000})
	if err != nil {
		t.Fatal(err)
	}
	assertGoldenEqual(t, goldenOrgTimeAggregate, r.SQL)
}

func TestGoldenSQL_AllShapesHaveOrgPredicate(t *testing.T) {
	t.Parallel()
	// Fixed allowlist — no user-controlled path segments (Codacy).
	names := []string{goldenOrgTimeAggregate}
	for _, name := range names {
		b, err := os.ReadFile(filepath.Join("testdata", name))
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(b), "org_id") {
			t.Fatalf("%s missing org_id", name)
		}
	}
}

func assertGoldenEqual(t *testing.T, name, sql string) {
	t.Helper()
	if name != goldenOrgTimeAggregate {
		t.Fatalf("unexpected golden basename %q", name)
	}
	want, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatalf("read golden: %v", err)
	}
	if !strings.Contains(sql, "org_id = ?") {
		t.Fatalf("rendered SQL missing org_id predicate:\n%s", sql)
	}
	if normalizeWS(sql) != normalizeWS(string(want)) {
		t.Fatalf("golden mismatch for %s\ngot:\n%s\nwant:\n%s", name, sql, want)
	}
}

func normalizeWS(s string) string {
	return strings.Join(strings.Fields(s), " ")
}
