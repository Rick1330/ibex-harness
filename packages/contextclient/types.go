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
	OrgID              string
	AgentID            string
	SessionID          string
	Model              string
	Query              string
	DirectiveVersionID string
	AvailableTokens    int32
	RecentMessages     []Message
	Options            AssembleOptions
	// 4.P.2 evidence-plane correlation (OTel TraceID/SpanID + request UUID v7).
	RequestID string
	TraceID   string
	SpanID    string
}

// MemoryUsed is one retrieval candidate returned by Assemble.
type MemoryUsed struct {
	MemoryID        string
	CompositeScore  float32
	RelevanceScore  float32
	RecencyScore    float32
	UsefulnessScore float32
	Rank            int32
	Category        string
	Exclusion       string
	Similarity      float32
	Confidence      float32
	TokenEstimate   int32
}

// AssemblyMetrics mirrors proto stage timings for durable persistence.
type AssemblyMetrics struct {
	BudgetCalculationMs   int32
	DirectiveLoadMs       int32
	HotMemoryRetrievalMs  int32
	ColdMemoryRetrievalMs int32
	RankingMs             int32
	PackingMs             int32
	FormattingMs          int32
	TotalMs               int32
	CandidatesEvaluated   int32
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
	MemoriesUsed     []MemoryUsed
	Metrics          *AssemblyMetrics
	RequestID        string
	TraceID          string
	SpanID           string
	ScoreSchema      string
	Fallback         bool
	FallbackReason   string
}
