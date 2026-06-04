package validation

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

func TestValidateChatCompletionRequest(t *testing.T) {
	temp := 3.0
	maxTok := 0
	tests := []struct {
		name    string
		req     *llm.ChatCompletionRequest
		wantLen int
		wantFld string
	}{
		{
			name:    "missing model",
			req:     &llm.ChatCompletionRequest{Messages: []llm.Message{{Role: "user", Content: "hi"}}},
			wantLen: 1,
			wantFld: "model",
		},
		{
			name:    "missing messages",
			req:     &llm.ChatCompletionRequest{Model: "gpt-4"},
			wantLen: 1,
			wantFld: "messages",
		},
		{
			name: "invalid role",
			req: &llm.ChatCompletionRequest{
				Model:    "gpt-4",
				Messages: []llm.Message{{Role: "human", Content: "hi"}},
			},
			wantLen: 1,
			wantFld: "messages[0].role",
		},
		{
			name: "valid minimal",
			req: &llm.ChatCompletionRequest{
				Model:    "gpt-4",
				Messages: []llm.Message{{Role: "user", Content: "hi"}},
			},
			wantLen: 0,
		},
		{
			name: "temperature out of range",
			req: &llm.ChatCompletionRequest{
				Model: "gpt-4", Messages: []llm.Message{{Role: "user", Content: "x"}},
				Temperature: &temp,
			},
			wantLen: 1,
			wantFld: "temperature",
		},
		{
			name: "max_tokens invalid",
			req: &llm.ChatCompletionRequest{
				Model: "gpt-4", Messages: []llm.Message{{Role: "user", Content: "x"}},
				MaxTokens: &maxTok,
			},
			wantLen: 1,
			wantFld: "max_tokens",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ValidateChatCompletionRequest(tt.req)
			if len(got) != tt.wantLen {
				t.Fatalf("len=%d want %d: %+v", len(got), tt.wantLen, got)
			}
			if tt.wantLen > 0 && got[0].Field != tt.wantFld {
				t.Fatalf("field=%s want %s", got[0].Field, tt.wantFld)
			}
		})
	}
}

func TestValidateChatCompletionRequest_aggregatesMultiple(t *testing.T) {
	req := &llm.ChatCompletionRequest{Model: "", Messages: nil}
	got := ValidateChatCompletionRequest(req)
	if len(got) < 2 {
		t.Fatalf("expected multiple errors, got %d", len(got))
	}
}

func TestValidateChatCompletionRequest_contentTooLong(t *testing.T) {
	req := &llm.ChatCompletionRequest{
		Model:    "gpt-4",
		Messages: []llm.Message{{Role: "user", Content: strings.Repeat("a", MaxMessageContentBytes+1)}},
	}
	got := ValidateChatCompletionRequest(req)
	if len(got) != 1 || got[0].Code != fieldCodeTooLong {
		t.Fatalf("got %+v", got)
	}
}
