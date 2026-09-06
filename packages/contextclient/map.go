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
		OrgId:          req.OrgID,
		AgentId:        req.AgentID,
		Model:          req.Model,
		Query:          req.Query,
		RecentMessages: msgs,
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
	return AssembleResult{
		AssembledContext: resp.GetAssembledContext(),
		TokensUsed:       resp.GetTokensUsed(),
		MemoriesIncluded: resp.GetMemoriesIncluded(),
		DirectiveTokens:  resp.GetDirectiveTokens(),
		HistoryTokens:    resp.GetHistoryTokens(),
		MemoryTokens:     resp.GetMemoryTokens(),
		Fallback:         false,
	}
}
