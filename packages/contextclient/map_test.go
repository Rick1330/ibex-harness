package contextclient

import (
	"testing"

	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
)

func TestUnit_ToProto_CorrelationFields(t *testing.T) {
	t.Parallel()
	pb := toProto(AssembleParams{
		OrgID: "o", AgentID: "a", Model: "m",
		RequestID: "rid", TraceID: "tid", SpanID: "sid",
		RecentMessages: []Message{{Role: "user", Content: "hi"}},
		Options:        AssembleOptions{MaxMemories: 3},
	})
	assertCorrelation(t, pb)
	assertMaxMemories(t, pb, 3)
}

func assertCorrelation(t *testing.T, pb *contextv1.AssembleContextRequest) {
	t.Helper()
	if pb.GetRequestId() != "rid" {
		t.Fatalf("request_id=%q", pb.GetRequestId())
	}
	if pb.GetTraceId() != "tid" {
		t.Fatalf("trace_id=%q", pb.GetTraceId())
	}
	if pb.GetSpanId() != "sid" {
		t.Fatalf("span_id=%q", pb.GetSpanId())
	}
}

func assertMaxMemories(t *testing.T, pb *contextv1.AssembleContextRequest, want int32) {
	t.Helper()
	if pb.GetOptions().GetMaxMemories() != want {
		t.Fatalf("max_memories=%d want %d", pb.GetOptions().GetMaxMemories(), want)
	}
}

func TestUnit_FromProto_NilFallback(t *testing.T) {
	t.Parallel()
	got := fromProto(nil)
	if !got.Fallback || got.FallbackReason != "nil_response" {
		t.Fatalf("%+v", got)
	}
}

func TestUnit_FromProto_MapsMetricsAndMemories(t *testing.T) {
	t.Parallel()
	got := fromProto(sampleAssembleResponse())
	assertMappedResult(t, got)
}

func sampleAssembleResponse() *contextv1.AssembleContextResponse {
	return &contextv1.AssembleContextResponse{
		AssembledContext: "ctx",
		TokensUsed:       10,
		MemoriesIncluded: 1,
		RequestId:        "r",
		TraceId:          "t",
		SpanId:           "s",
		ScoreSchema:      "interim_v1",
		Metrics: &contextv1.AssemblyMetrics{
			TotalMs: 12, RankingMs: 3, CandidatesEvaluated: 2,
		},
		MemoriesUsed: []*contextv1.MemoryUsed{
			{
				MemoryId: "11111111-1111-1111-1111-111111111111",
				Rank:     1, Exclusion: "included", Similarity: 0.9, Confidence: 0.8,
			},
			nil,
		},
	}
}

func assertMappedResult(t *testing.T, got AssembleResult) {
	t.Helper()
	if got.AssembledContext != "ctx" || got.RequestID != "r" || got.TraceID != "t" {
		t.Fatalf("%+v", got)
	}
	if got.Metrics == nil || got.Metrics.TotalMs != 12 {
		t.Fatalf("metrics=%+v", got.Metrics)
	}
	if len(got.MemoriesUsed) != 1 || got.MemoriesUsed[0].Exclusion != "included" {
		t.Fatalf("memories=%+v", got.MemoriesUsed)
	}
}
