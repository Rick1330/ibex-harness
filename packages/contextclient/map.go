package contextclient

import (
	contextv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/context/v1"
)

func toProto(req AssembleParams) *contextv1.AssembleContextRequest {
	msgs := make([]*contextv1.Message, 0, len(req.RecentMessages))
	for _, m := range req.RecentMessages {
		msgs = append(msgs, &contextv1.Message{Role: m.Role, Content: m.Content})
	}
	out := &contextv1.AssembleContextRequest{
		OrgId:              req.OrgID,
		AgentId:            req.AgentID,
		SessionId:          req.SessionID,
		Model:              req.Model,
		Query:              req.Query,
		DirectiveVersionId: req.DirectiveVersionID,
		AvailableTokens:    req.AvailableTokens,
		RequestId:          req.RequestID,
		TraceId:            req.TraceID,
		SpanId:             req.SpanID,
		RecentMessages:     msgs,
		Options: &contextv1.AssemblyOptions{
			SkipColdMemories: req.Options.SkipColdMemories,
			SkipHotMemories:  req.Options.SkipHotMemories,
			MaxMemories:      req.Options.MaxMemories,
		},
	}
	return out
}

func fromProto(resp *contextv1.AssembleContextResponse) AssembleResult {
	if resp == nil {
		return AssembleResult{Fallback: true, FallbackReason: "nil_response"}
	}
	memories := make([]MemoryUsed, 0, len(resp.GetMemoriesUsed()))
	for _, m := range resp.GetMemoriesUsed() {
		if m == nil {
			continue
		}
		memories = append(memories, MemoryUsed{
			MemoryID:        m.GetMemoryId(),
			CompositeScore:  m.GetCompositeScore(),
			RelevanceScore:  m.GetRelevanceScore(),
			RecencyScore:    m.GetRecencyScore(),
			UsefulnessScore: m.GetUsefulnessScore(),
			Rank:            m.GetRank(),
			Category:        m.GetCategory(),
			Exclusion:       m.GetExclusion(),
			Similarity:      m.GetSimilarity(),
			Confidence:      m.GetConfidence(),
			TokenEstimate:   m.GetTokenEstimate(),
		})
	}
	var metrics *AssemblyMetrics
	if m := resp.GetMetrics(); m != nil {
		metrics = &AssemblyMetrics{
			BudgetCalculationMs:   m.GetBudgetCalculationMs(),
			DirectiveLoadMs:       m.GetDirectiveLoadMs(),
			HotMemoryRetrievalMs:  m.GetHotMemoryRetrievalMs(),
			ColdMemoryRetrievalMs: m.GetColdMemoryRetrievalMs(),
			RankingMs:             m.GetRankingMs(),
			PackingMs:             m.GetPackingMs(),
			FormattingMs:          m.GetFormattingMs(),
			TotalMs:               m.GetTotalMs(),
			CandidatesEvaluated:   m.GetCandidatesEvaluated(),
		}
	}
	return AssembleResult{
		AssembledContext: resp.GetAssembledContext(),
		TokensUsed:       resp.GetTokensUsed(),
		MemoriesIncluded: resp.GetMemoriesIncluded(),
		DirectiveTokens:  resp.GetDirectiveTokens(),
		HistoryTokens:    resp.GetHistoryTokens(),
		MemoryTokens:     resp.GetMemoryTokens(),
		MemoriesUsed:     memories,
		Metrics:          metrics,
		RequestID:        resp.GetRequestId(),
		TraceID:          resp.GetTraceId(),
		SpanID:           resp.GetSpanId(),
		ScoreSchema:      resp.GetScoreSchema(),
		Fallback:         false,
	}
}
