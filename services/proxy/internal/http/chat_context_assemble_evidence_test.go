package http

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/contextclient"
	"github.com/Rick1330/ibex-harness/packages/evidenceoutbox"
)

func TestUnit_FinalRankForExclusion(t *testing.T) {
	t.Parallel()
	if got := finalRankForExclusion("budget", 2); got != nil {
		t.Fatalf("budget FinalRank=%v want nil", got)
	}
	if got := finalRankForExclusion("excluded", 3); got != nil {
		t.Fatalf("excluded FinalRank=%v want nil", got)
	}
	got := finalRankForExclusion("included", 1)
	if got == nil || *got != 1 {
		t.Fatalf("included FinalRank=%v", got)
	}
}

func TestUnit_EvidenceExtrasFromAssemble_Metrics(t *testing.T) {
	t.Parallel()
	extras := evidenceExtrasFromAssemble(sampleAssembleResult())
	if extras.Metrics == nil || extras.Metrics.TotalMs != 9 {
		t.Fatalf("metrics=%+v", extras.Metrics)
	}
	if len(extras.Candidates) != 3 {
		t.Fatalf("candidates=%d", len(extras.Candidates))
	}
}

func TestUnit_EvidenceExtrasFromAssemble_FinalRankPackOrder(t *testing.T) {
	t.Parallel()
	extras := evidenceExtrasFromAssemble(sampleAssembleResult())
	assertFinalRank(t, extras.Candidates[0].FinalRank, 1, "first included")
	if extras.Candidates[1].FinalRank != nil {
		t.Fatalf("budget FinalRank=%v want nil", extras.Candidates[1].FinalRank)
	}
	assertFinalRank(t, extras.Candidates[2].FinalRank, 2, "second included")
}

func sampleAssembleResult() contextclient.AssembleResult {
	return contextclient.AssembleResult{
		ScoreSchema: evidenceoutbox.ScoreSchemaInterim,
		Metrics:     &contextclient.AssemblyMetrics{TotalMs: 9, RankingMs: 2},
		MemoriesUsed: []contextclient.MemoryUsed{
			{
				MemoryID: "11111111-1111-1111-1111-111111111111",
				Rank:     5, Exclusion: "included", Similarity: 0.9, Confidence: 0.8,
				CompositeScore: 0.85, TokenEstimate: 10, Category: "fact",
			},
			{
				MemoryID: "22222222-2222-2222-2222-222222222222",
				Rank:     2, Exclusion: "budget", Similarity: 0.7, Confidence: 0.6,
				CompositeScore: 0.65, TokenEstimate: 8,
			},
			{
				MemoryID: "33333333-3333-3333-3333-333333333333",
				Rank:     9, Exclusion: "included", Similarity: 0.5, Confidence: 0.5,
				CompositeScore: 0.5, TokenEstimate: 4,
			},
		},
	}
}

func assertFinalRank(t *testing.T, got *int, want int, label string) {
	t.Helper()
	if got == nil || *got != want {
		t.Fatalf("%s FinalRank=%v want %d", label, got, want)
	}
}
