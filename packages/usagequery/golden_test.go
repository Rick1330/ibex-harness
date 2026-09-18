package usagequery

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

// Hardcoded relative path — never construct from a variable (Codacy path traversal).
const goldenOrgTimePath = "testdata/org_time_aggregate.sql"

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
	assertGoldenEqual(t, r.SQL)
}

func TestRenderAgentSession_CompletenessAllRows(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	agent := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := start.Add(24 * time.Hour)
	r, err := RenderSQL(Query{
		Shape: ShapeAgentSessionBreakdown, OrgID: org, AgentID: &agent,
		Start: start, End: end, Limit: 50,
	}, BudgetLimits{MaxRows: 10000})
	if err != nil {
		t.Fatal(err)
	}
	assertCompletenessAllRowsExpr(t, r.SQL)
}

func TestRenderFallback_CompletenessAllRows(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := start.Add(24 * time.Hour)
	r, err := RenderSQL(Query{
		Shape: ShapeFallbackAttribution, OrgID: org, Start: start, End: end, Limit: 50,
	}, BudgetLimits{MaxRows: 10000})
	if err != nil {
		t.Fatal(err)
	}
	assertCompletenessAllRowsExpr(t, r.SQL)
}

func TestGoldenSQL_OrgTimeHasOrgPredicate(t *testing.T) {
	t.Parallel()
	b, err := os.ReadFile(goldenOrgTimePath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(b), "org_id") {
		t.Fatalf("%s missing org_id", filepath.Base(goldenOrgTimePath))
	}
}

func assertCompletenessAllRowsExpr(t *testing.T, sql string) {
	t.Helper()
	want := "if(countIf(completeness != 'complete') = 0, 'complete', 'partial')"
	if !strings.Contains(sql, want) {
		t.Fatalf("missing all-rows completeness expression\ngot:\n%s", sql)
	}
	if strings.Contains(sql, "any(completeness)") {
		t.Fatalf("legacy any(completeness) must not appear:\n%s", sql)
	}
}

func assertGoldenEqual(t *testing.T, sql string) {
	t.Helper()
	want, err := os.ReadFile(goldenOrgTimePath)
	if err != nil {
		t.Fatalf("read golden: %v", err)
	}
	if !strings.Contains(sql, "org_id = ?") {
		t.Fatalf("rendered SQL missing org_id predicate:\n%s", sql)
	}
	if normalizeWS(sql) != normalizeWS(string(want)) {
		t.Fatalf("golden mismatch\ngot:\n%s\nwant:\n%s", sql, want)
	}
}

func normalizeWS(s string) string {
	return strings.Join(strings.Fields(s), " ")
}
