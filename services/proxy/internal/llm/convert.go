package llm

import "github.com/Rick1330/ibex-harness/packages/provider"

// ToProviderRequest converts a parsed chat body to the provider-neutral request shape.
func ToProviderRequest(parsed *ChatCompletionRequest) provider.Request {
	if parsed == nil {
		return provider.Request{}
	}
	out := provider.Request{
		Model:       parsed.Model,
		Stream:      parsed.Stream,
		Temperature: parsed.Temperature,
	}
	if parsed.MaxTokens != nil {
		out.MaxTokens = *parsed.MaxTokens
	}
	out.Messages = make([]provider.Message, len(parsed.Messages))
	for i, msg := range parsed.Messages {
		out.Messages[i] = provider.Message{Role: msg.Role, Content: msg.Content}
	}
	return out
}
