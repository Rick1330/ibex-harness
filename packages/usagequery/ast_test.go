package usagequery

import (
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestValidate_RequiresOrgID(t *testing.T) {
	t.Parallel()
	err := Validate(Query{
		Shape: ShapeOrgTimeAggregate,
		Start: time.Now().Add(-time.Hour),
		End:   time.Now(),
	}, BudgetLimits{})
	if err == nil || !strings.Contains(err.Error(), "org_id") {
		t.Fatalf("err=%v", err)
	}
}

func TestValidate_RejectsUnboundedRange(t *testing.T) {
	t.Parallel()
	err := Validate(Query{
		Shape: ShapeOrgTimeAggregate,
		OrgID: uuid.New(),
		Start: time.Now().Add(-40 * 24 * time.Hour),
		End:   time.Now(),
	}, BudgetLimits{MaxTimeRange: 31 * 24 * time.Hour})
	if err == nil {
		t.Fatal("expected time range error")
	}
}

func TestRenderSQL_AlwaysIncludesOrgPredicate(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	start := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	end := start.Add(24 * time.Hour)
	for _, shape := range []Shape{
		ShapeOrgTimeAggregate,
		ShapeAgentSessionBreakdown,
		ShapeFallbackAttribution,
		ShapeToolCorrelation,
	} {
		r, err := RenderSQL(Query{Shape: shape, OrgID: org, Start: start, End: end, Limit: 100}, BudgetLimits{})
		if err != nil {
			t.Fatalf("%s: %v", shape, err)
		}
		if !strings.Contains(r.SQL, "org_id = ?") {
			t.Fatalf("%s missing org_id predicate: %s", shape, r.SQL)
		}
		if len(r.Args) < 1 || r.Args[0] != org {
			t.Fatalf("%s args[0]=%v", shape, r.Args)
		}
		if !strings.Contains(r.SQL, "max_rows_to_read") {
			t.Fatalf("%s missing max_rows_to_read", shape)
		}
	}
}

func TestRenderSQL_RequestPoint(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	start := time.Now().UTC().Add(-time.Hour)
	end := time.Now().UTC()
	_, err := RenderSQL(Query{
		Shape: ShapeRequestPointLookup, OrgID: org, Start: start, End: end,
	}, BudgetLimits{})
	if err == nil {
		t.Fatal("expected request_id required")
	}
	r, err := RenderSQL(Query{
		Shape: ShapeRequestPointLookup, OrgID: org, Start: start, End: end, RequestID: "r1",
	}, BudgetLimits{})
	if err != nil {
		t.Fatal(err)
	}
	if r.Args[1] != "r1" {
		t.Fatalf("args=%v", r.Args)
	}
}

func TestInflightKey(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	if got := InflightKey(org); got != "org_id:22222222-2222-2222-2222-222222222222:usagequery:inflight" {
		t.Fatalf("got %s", got)
	}
}
