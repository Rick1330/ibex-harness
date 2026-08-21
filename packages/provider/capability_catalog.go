package provider

// Built-in capability rows are hand-verified against vendor docs (ADR-0041).
// Sources (as of 2026-08):
//   - OpenAI GPT-4o / GPT-4o-mini: 128k context, 16_384 max output, o200k_base
//   - OpenAI GPT-4 Turbo: 128k context, 4_096 max output, cl100k_base
//   - OpenAI GPT-3.5 Turbo: 16_385 context, 4_096 max output, cl100k_base
//   - Anthropic Claude Sonnet/Haiku/Opus 4.5: 200k context, 64k max output, family "claude"
//
// SupportsTools/SupportsVision reflect vendor model truth, not adapter feature
// completeness (Anthropic tool/image passthrough may still be deferred).

type capabilityRow struct {
	modelID   string
	provider  string
	ctx       int
	maxOut    int
	tools     bool
	vision    bool
	tokenizer string
}

func BuiltInCapabilityCatalog() CapabilityCatalog {
	rows := []capabilityRow{
		{modelID: "gpt-4o", provider: "openai", ctx: 128_000, maxOut: 16_384, tools: true, vision: true, tokenizer: TokenizerFamilyO200kBase},
		{modelID: "gpt-4o-mini", provider: "openai", ctx: 128_000, maxOut: 16_384, tools: true, vision: true, tokenizer: TokenizerFamilyO200kBase},
		{modelID: "gpt-4-turbo", provider: "openai", ctx: 128_000, maxOut: 4_096, tools: true, vision: true, tokenizer: TokenizerFamilyCL100kBase},
		{modelID: "gpt-3.5-turbo", provider: "openai", ctx: 16_385, maxOut: 4_096, tools: true, vision: false, tokenizer: TokenizerFamilyCL100kBase},
		{modelID: "claude-sonnet-4-5", provider: "anthropic", ctx: 200_000, maxOut: 64_000, tools: true, vision: true, tokenizer: TokenizerFamilyClaude},
		{modelID: "claude-haiku-4-5", provider: "anthropic", ctx: 200_000, maxOut: 64_000, tools: true, vision: true, tokenizer: TokenizerFamilyClaude},
		{modelID: "claude-opus-4-5", provider: "anthropic", ctx: 200_000, maxOut: 64_000, tools: true, vision: true, tokenizer: TokenizerFamilyClaude},
	}
	caps := make([]ModelCapability, 0, len(rows))
	for _, row := range rows {
		caps = append(caps, capabilityFromRow(row))
	}
	return CatalogFromCapabilities(caps...)
}

func capabilityFromRow(row capabilityRow) ModelCapability {
	return ModelCapability{
		ModelID:           row.modelID,
		Provider:          row.provider,
		ContextWindow:     row.ctx,
		MaxOutputTokens:   row.maxOut,
		SupportsTools:     row.tools,
		SupportsVision:    row.vision,
		SupportsStreaming: true,
		TokenizerFamily:   row.tokenizer,
	}
}
