package contextclient

// Message is a chat turn passed to AssembleContext (role/content only).
type Message struct {
	Role    string
	Content string
}

// AssembleOptions maps the subset of AssemblyOptions the C.6 server reads today.
type AssembleOptions struct {
	SkipColdMemories bool
	SkipHotMemories  bool
	MaxMemories      int32
}

// AssembleParams is the domain request for Client.Assemble (hides proto wire types).
type AssembleParams struct {
	OrgID          string
	AgentID        string
	Model          string
	Query          string
	RecentMessages []Message
	Options        AssembleOptions
	// TODO(3.5.D.x): populate SessionID, DirectiveVersionID, AvailableTokens, and score-weight
	// options when the context server reads those AssembleContextRequest fields.
}

// AssembleResult is the fail-open outcome of Client.Assemble.
// Fallback=true means the LLM path must proceed without assembled context
// (distinct from a successful call that returned empty memories / L2).
type AssembleResult struct {
	AssembledContext string
	TokensUsed       int32
	MemoriesIncluded int32
	DirectiveTokens  int32
	HistoryTokens    int32
	MemoryTokens     int32
	Fallback         bool
	FallbackReason   string
}
