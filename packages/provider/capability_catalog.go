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

func BuiltInCapabilityCatalog() CapabilityCatalog {
	return CatalogFromCapabilities(
		openaiCap("gpt-4o", 128_000, 16_384, true, true, TokenizerFamilyO200kBase),
		openaiCap("gpt-4o-mini", 128_000, 16_384, true, true, TokenizerFamilyO200kBase),
		openaiCap("gpt-4-turbo", 128_000, 4_096, true, true, TokenizerFamilyCL100kBase),
		openaiCap("gpt-3.5-turbo", 16_385, 4_096, true, false, TokenizerFamilyCL100kBase),
		anthropicCap("claude-sonnet-4-5", 200_000, 64_000),
		anthropicCap("claude-haiku-4-5", 200_000, 64_000),
		anthropicCap("claude-opus-4-5", 200_000, 64_000),
	)
}

func openaiCap(modelID string, ctx, maxOut int, tools, vision bool, tokenizer string) ModelCapability {
	return ModelCapability{
		ModelID:           modelID,
		Provider:          "openai",
		ContextWindow:     ctx,
		MaxOutputTokens:   maxOut,
		SupportsTools:     tools,
		SupportsVision:    vision,
		SupportsStreaming: true,
		TokenizerFamily:   tokenizer,
	}
}

func anthropicCap(modelID string, ctx, maxOut int) ModelCapability {
	return ModelCapability{
		ModelID:           modelID,
		Provider:          "anthropic",
		ContextWindow:     ctx,
		MaxOutputTokens:   maxOut,
		SupportsTools:     true, // vendor model supports tools; adapter passthrough may lag
		SupportsVision:    true,
		SupportsStreaming: true,
		TokenizerFamily:   TokenizerFamilyClaude,
	}
}
