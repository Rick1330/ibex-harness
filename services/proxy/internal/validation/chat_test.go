package validation

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

func assertFieldError(t *testing.T, got []apierror.FieldError, field, code string) {
	t.Helper()
	if len(got) != 1 {
		t.Fatalf("len: %d", len(got))
	}
	if got[0].Field != field {
		t.Fatalf("field: %s", got[0].Field)
	}
	if got[0].Code != code {
		t.Fatalf("code: %s", got[0].Code)
	}
}

func TestValidateChatCompletionRequest(t *testing.T) {
	t.Parallel()

	temp := 3.0
	maxTok := 0
	tests := []struct {
		name    string
		req     *llm.ChatCompletionRequest
		wantLen int
		wantFld string
	}{
		{
			name:    "missing model allowed at parse",
			req:     &llm.ChatCompletionRequest{Messages: []llm.Message{{Role: "user", Content: "hi"}}},
			wantLen: 0,
			wantFld: "",
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
	temp := 9.0
	req := &llm.ChatCompletionRequest{Model: "gpt-4", Messages: nil, Temperature: &temp}
	got := ValidateChatCompletionRequest(req)
	if len(got) < 2 {
		t.Fatalf("expected multiple errors, got %d", len(got))
	}
}

func TestValidateChatCompletionRequest_nilRequest(t *testing.T) {
	got := ValidateChatCompletionRequest(nil)
	if len(got) != 1 {
		t.Fatalf("len: %d", len(got))
	}
	if got[0].Field != "body" {
		t.Fatalf("field: %s", got[0].Field)
	}
	if got[0].Code != fieldCodeRequired {
		t.Fatalf("code: %s", got[0].Code)
	}
}

func TestValidateChatCompletionRequest_modelTooLong(t *testing.T) {
	req := &llm.ChatCompletionRequest{
		Model:    strings.Repeat("m", MaxModelNameLength+1),
		Messages: []llm.Message{{Role: "user", Content: "hi"}},
	}
	assertFieldError(t, ValidateChatCompletionRequest(req), "model", fieldCodeTooLong)
}

func TestValidateChatCompletionRequest_tooManyMessages(t *testing.T) {
	msgs := make([]llm.Message, MaxMessagesPerRequest+1)
	for i := range msgs {
		msgs[i] = llm.Message{Role: "user", Content: "x"}
	}
	got := ValidateChatCompletionRequest(&llm.ChatCompletionRequest{Model: "gpt-4", Messages: msgs})
	found := false
	for _, fe := range got {
		if fe.Field == "messages" && fe.Code == fieldCodeTooMany {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected TOO_MANY on messages: %+v", got)
	}
}

func TestValidateChatCompletionRequest_maxTokensTooHigh(t *testing.T) {
	high := MaxChatMaxTokens + 1
	assertFieldError(t, ValidateChatCompletionRequest(&llm.ChatCompletionRequest{
		Model: "gpt-4", Messages: []llm.Message{{Role: "user", Content: "x"}},
		MaxTokens: &high,
	}), "max_tokens", fieldCodeTooLong)
}

func TestValidateChatCompletionRequest_emptyRole(t *testing.T) {
	got := ValidateChatCompletionRequest(&llm.ChatCompletionRequest{
		Model: "gpt-4", Messages: []llm.Message{{Role: "  ", Content: "hi"}},
	})
	if len(got) != 1 || got[0].Field != "messages[0].role" {
		t.Fatalf("got %+v", got)
	}
}

func TestValidateChatCompletionRequest_whitespaceModel(t *testing.T) {
	got := ValidateChatCompletionRequest(&llm.ChatCompletionRequest{
		Model: "   ", Messages: []llm.Message{{Role: "user", Content: "hi"}},
	})
	if len(got) != 0 {
		t.Fatalf("empty/whitespace model deferred to routing: got %+v", got)
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
