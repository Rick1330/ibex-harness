package trace

import (
	"reflect"
	"testing"
	"time"

	ibexch "github.com/Rick1330/ibex-harness/packages/clickhouse"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/google/uuid"
)

func TestUnit_Assemble_MapsFields(t *testing.T) {
	t.Parallel()
	ids := assembleWantIDs{
		org:   uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		agent: uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		sid:   uuid.MustParse("33333333-3333-3333-3333-333333333333"),
	}
	start := time.Date(2026, 7, 25, 12, 0, 0, 0, time.UTC)
	end := start.Add(150 * time.Millisecond)

	rec := Assemble(AssembleInput{
		RequestID: "req-1", OrgID: ids.org, AgentID: ids.agent, SessionID: &ids.sid,
		Model: "gpt-4o", Provider: "openai", Streaming: true,
		Usage: &provider.Usage{InputTokens: 10, OutputTokens: 20, TotalTokens: 30},
		Timings: RequestTimings{
			AuthMs: 5, DirectiveMs: 7, ProviderTTFB: 40 * time.Millisecond,
			RequestedAt: start, CompletedAt: end,
		},
		Outcome: RequestOutcome{StatusCode: 200, IsComplete: true},
	})
	assertAssembleIDs(t, rec, ids)
	assertAssembleTokens(t, rec)
	assertAssembleLatencies(t, rec)
	assertNoContentFields(t, rec)
}

type assembleWantIDs struct {
	org, agent, sid uuid.UUID
}

func assertAssembleIDs(t *testing.T, rec ibexch.TraceRecord, ids assembleWantIDs) {
	t.Helper()
	if rec.RequestID != "req-1" {
		t.Fatalf("request_id=%s", rec.RequestID)
	}
	if rec.OrgID != ids.org {
		t.Fatalf("org=%s", rec.OrgID)
	}
	if rec.AgentID != ids.agent {
		t.Fatalf("agent=%s", rec.AgentID)
	}
	if rec.SessionID == nil || *rec.SessionID != ids.sid {
		t.Fatalf("session=%v", rec.SessionID)
	}
}

func assertAssembleTokens(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	if rec.InputTokens != 10 {
		t.Fatalf("input tokens=%d", rec.InputTokens)
	}
	if rec.OutputTokens != 20 {
		t.Fatalf("output tokens=%d", rec.OutputTokens)
	}
	if rec.TotalTokens != 30 {
		t.Fatalf("total tokens=%d", rec.TotalTokens)
	}
	if !rec.IsStreaming {
		t.Fatal("expected streaming")
	}
	if !rec.IsComplete {
		t.Fatal("expected complete")
	}
	if rec.Model != "gpt-4o" {
		t.Fatalf("model=%s", rec.Model)
	}
	if rec.Provider != "openai" {
		t.Fatalf("provider=%s", rec.Provider)
	}
}

func assertAssembleLatencies(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	if rec.AuthLatencyMs != 5 {
		t.Fatalf("auth ms=%d", rec.AuthLatencyMs)
	}
	if rec.DirectiveLatencyMs != 7 {
		t.Fatalf("directive ms=%d", rec.DirectiveLatencyMs)
	}
	if rec.ProviderTTFBMs != 40 {
		t.Fatalf("ttfb=%d", rec.ProviderTTFBMs)
	}
	if rec.TotalLatencyMs != 150 {
		t.Fatalf("total_ms=%d", rec.TotalLatencyMs)
	}
}

func TestUnit_Assemble_NilUsageZeros(t *testing.T) {
	t.Parallel()
	rec := Assemble(AssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Timings: RequestTimings{CompletedAt: time.Now().UTC()},
		Outcome: RequestOutcome{StatusCode: 502, IsComplete: false, ErrorCode: "PROVIDER_UNAVAILABLE"},
	})
	if rec.TotalTokens != 0 {
		t.Fatalf("tokens=%d", rec.TotalTokens)
	}
	if rec.IsComplete {
		t.Fatal("expected incomplete")
	}
	if rec.ErrorCode == "" {
		t.Fatal("expected error_code")
	}
}

func TestUnit_Assemble_DefaultsAndUsageSum(t *testing.T) {
	t.Parallel()
	rec := Assemble(AssembleInput{
		RequestID: "r", OrgID: uuid.New(), AgentID: uuid.New(),
		Usage:   &provider.Usage{InputTokens: 3, OutputTokens: 4},
		Timings: RequestTimings{},
		Outcome: RequestOutcome{StatusCode: 0, IsComplete: true},
	})
	if rec.TotalTokens != 7 {
		t.Fatalf("sum total=%d", rec.TotalTokens)
	}
	if rec.RequestedAt.IsZero() {
		t.Fatal("requested_at")
	}
	if rec.CompletedAt.IsZero() {
		t.Fatal("completed_at")
	}
}

func TestUnit_AddUint32Sat_Overflow(t *testing.T) {
	t.Parallel()
	got := addUint32Sat(^uint32(0), ^uint32(0))
	if got != ^uint32(0) {
		t.Fatalf("got=%d", got)
	}
	if addUint32Sat(1, 2) != 3 {
		t.Fatal("sum")
	}
}

func TestUnit_ClampHelpers(t *testing.T) {
	t.Parallel()
	if durationToUint32(-time.Second) != 0 {
		t.Fatal("neg duration")
	}
	overU32 := (time.Duration(^uint32(0)) + 1) * time.Millisecond
	if durationToUint32(overU32) != ^uint32(0) {
		t.Fatal("duration overflow")
	}
	if intToUint32(-1) != 0 {
		t.Fatal("neg int")
	}
	if intToUint32(int(^uint32(0))+1) != ^uint32(0) {
		t.Fatal("int overflow")
	}
	if ClampUint16Ms(-time.Millisecond) != 0 {
		t.Fatal("neg clamp")
	}
	overU16 := (time.Duration(^uint16(0)) + 1) * time.Millisecond
	if ClampUint16Ms(overU16) != ^uint16(0) {
		t.Fatal("clamp overflow")
	}
}

func assertNoContentFields(t *testing.T, rec ibexch.TraceRecord) {
	t.Helper()
	forbidden := map[string]struct{}{
		"Prompt": {}, "Completion": {}, "Content": {}, "Messages": {},
	}
	rt := reflect.TypeOf(rec)
	for i := 0; i < rt.NumField(); i++ {
		name := rt.Field(i).Name
		if _, ok := forbidden[name]; ok {
			t.Fatalf("forbidden field %s", name)
		}
	}
}
