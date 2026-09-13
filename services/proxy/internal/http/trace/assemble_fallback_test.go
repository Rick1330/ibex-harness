package trace

import (
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/google/uuid"
)

type wantFallbackAudit struct {
	original string
	fallback string
	reason   string
}

func TestUnit_Assemble_FallbackAuditFields(t *testing.T) {
	t.Parallel()
	rec := Assemble(AssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Model: "claude-sonnet-4-5", Provider: "anthropic",
		OriginalModel: "gpt-4o", FallbackModel: "claude-sonnet-4-5",
		FallbackReason: "provider_5xx",
		Timings:        RequestTimings{CompletedAt: time.Now().UTC()},
		Outcome:        RequestOutcome{StatusCode: 200, IsComplete: true},
	})
	assertFallbackAudit(t, rec, wantFallbackAudit{
		original: "gpt-4o", fallback: "claude-sonnet-4-5", reason: "provider_5xx",
	})
}

func TestUnit_Assemble_NonFallbackLeavesAuditEmpty(t *testing.T) {
	t.Parallel()
	plain := Assemble(AssembleInput{
		RequestID: "r2", OrgID: uuid.New(), AgentID: uuid.New(),
		Model:   "gpt-4o",
		Timings: RequestTimings{CompletedAt: time.Now().UTC()},
		Outcome: RequestOutcome{StatusCode: 200, IsComplete: true},
	})
	if plain.OriginalModel != nil {
		t.Fatalf("original=%v", plain.OriginalModel)
	}
	if plain.FallbackModel != nil {
		t.Fatalf("fallback=%v", plain.FallbackModel)
	}
	if plain.FallbackReason != "" {
		t.Fatalf("reason=%q", plain.FallbackReason)
	}
}

func assertFallbackAudit(t *testing.T, rec ibexch.TraceRecord, want wantFallbackAudit) {
	t.Helper()
	if rec.Model != want.fallback {
		t.Fatalf("model=%s", rec.Model)
	}
	if rec.OriginalModel == nil {
		t.Fatal("original nil")
	}
	if *rec.OriginalModel != want.original {
		t.Fatalf("original=%q", *rec.OriginalModel)
	}
	if rec.FallbackModel == nil {
		t.Fatal("fallback nil")
	}
	if *rec.FallbackModel != want.fallback {
		t.Fatalf("fallback=%q", *rec.FallbackModel)
	}
	if rec.FallbackReason != want.reason {
		t.Fatalf("reason=%q", rec.FallbackReason)
	}
}
