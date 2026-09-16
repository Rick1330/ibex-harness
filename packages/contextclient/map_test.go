package contextclient

import (
	"testing"

	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
)

func TestUnit_ToProto_CorrelationFields(t *testing.T) {
	t.Parallel()
	req := AssembleParams{
		OrgID: "o", AgentID: "a", Model: "m",
		RequestID: "rid", TraceID: "tid", SpanID: "sid",
		RecentMessages: []Message{{Role: "user", Content: "hi"}},
		Options:        AssembleOptions{MaxMemories: 3},
	}
	pb := toProto(req)
	if pb.GetRequestId() != "rid" || pb.GetTraceId() != "tid" || pb.GetSpanId() != "sid" {
		t.Fatalf("correlation: %+v", pb)
	}
	if pb.GetOptions().GetMaxMemories() != 3 {
		t.Fatalf("options: %+v", pb.GetOptions())
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
	resp := &contextv1.AssembleContextResponse{
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
	got := fromProto(resp)
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
