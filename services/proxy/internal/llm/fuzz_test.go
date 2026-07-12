package llm

import (
	"strings"
	"testing"
)

func FuzzParseChatCompletionRequest(f *testing.F) {
	f.Add(`{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`)
	f.Add(`{"model":"m","messages":[]}`)
	f.Add(`{invalid`)
	f.Fuzz(func(t *testing.T, data string) {
		_, _ = ParseChatCompletionRequest(strings.NewReader(data))
	})
}
