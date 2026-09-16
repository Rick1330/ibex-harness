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
	got = finalRankForExclusion("", 4)
	if got == nil || *got != 4 {
		t.Fatalf("empty exclusion treated as included: %v", got)
	}
}

func TestUnit_EvidenceExtrasFromAssemble_FinalRankAndMetrics(t *testing.T) {
	t.Parallel()
	result := contextclient.AssembleResult{
		ScoreSchema: evidenceoutbox.ScoreSchemaInterim,
		Metrics:     &contextclient.AssemblyMetrics{TotalMs: 9, RankingMs: 2},
		MemoriesUsed: []contextclient.MemoryUsed{
			{
				MemoryID: "11111111-1111-1111-1111-111111111111",
				Rank:     1, Exclusion: "included", Similarity: 0.9, Confidence: 0.8,
				CompositeScore: 0.85, TokenEstimate: 10, Category: "fact",
			},
			{
				MemoryID: "22222222-2222-2222-2222-222222222222",
				Rank:     2, Exclusion: "budget", Similarity: 0.7, Confidence: 0.6,
				CompositeScore: 0.65, TokenEstimate: 8,
			},
		},
	}
	extras := evidenceExtrasFromAssemble(result)
	if extras.Metrics == nil || extras.Metrics.TotalMs != 9 {
		t.Fatalf("metrics=%+v", extras.Metrics)
	}
	if len(extras.Candidates) != 2 {
		t.Fatalf("candidates=%d", len(extras.Candidates))
	}
	if extras.Candidates[0].FinalRank == nil || *extras.Candidates[0].FinalRank != 1 {
		t.Fatalf("included FinalRank=%v", extras.Candidates[0].FinalRank)
	}
	if extras.Candidates[1].FinalRank != nil {
		t.Fatalf("budget FinalRank=%v want nil", extras.Candidates[1].FinalRank)
	}
}
