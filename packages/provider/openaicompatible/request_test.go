package openaicompatible

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestMarshalRequest_passthroughAndDenylist(t *testing.T) {
	t.Parallel()
	temp := 0.5
	raw, err := marshalOpenAIRequestBody(provider.Request{
		Model:       "gpt-4o",
		MaxTokens:   100,
		Temperature: &temp,
		Messages:    []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{
			"model": "evil", "top_p": 0.9, "stream": true,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	body := string(raw)
	if !strings.Contains(body, `"model":"gpt-4o"`) || !strings.Contains(body, `"top_p":0.9`) {
		t.Fatalf("body=%s", body)
	}
	if strings.Contains(body, `"stream":true`) {
		t.Fatal("stream override must be denied")
	}
}
