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
	if got.Model != "gpt-4o" {
		t.Fatalf("model: %q", got.Model)
	}
	if got.MaxTokens != 42 {
		t.Fatalf("max tokens: %d", got.MaxTokens)
	}
	if got.Stream {
		t.Fatal("stream should be false")
	}
	if len(got.Messages) != 1 {
		t.Fatalf("messages: %+v", got.Messages)
	}
	if got.Messages[0].Content != "hi" {
		t.Fatalf("message content: %q", got.Messages[0].Content)
	}
}

func TestToProviderRequest_nilMaxTokens(t *testing.T) {
	t.Parallel()
	got := ToProviderRequest(&ChatCompletionRequest{Model: "gpt-4o"})
	if got.MaxTokens != 0 {
		t.Fatalf("max tokens: %d", got.MaxTokens)
	}
}
