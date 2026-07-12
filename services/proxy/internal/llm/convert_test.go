package llm

import "testing"

func TestToProviderRequest_mapsFields(t *testing.T) {
	t.Parallel()
	maxTokens := 42
	temp := 0.5
	got := ToProviderRequest(&ChatCompletionRequest{
		Model:       "gpt-4o",
		Stream:      false,
		Temperature: &temp,
		MaxTokens:   &maxTokens,
		Messages:    []Message{{Role: "user", Content: "hi"}},
	})
	if got.Model != "gpt-4o" || got.MaxTokens != 42 || got.Stream {
		t.Fatalf("unexpected request: %+v", got)
	}
	if len(got.Messages) != 1 || got.Messages[0].Content != "hi" {
		t.Fatalf("messages: %+v", got.Messages)
	}
}

func TestToProviderRequest_nilMaxTokens(t *testing.T) {
	t.Parallel()
	got := ToProviderRequest(&ChatCompletionRequest{Model: "gpt-4o"})
	if got.MaxTokens != 0 {
		t.Fatalf("max tokens: %d", got.MaxTokens)
	}
}
