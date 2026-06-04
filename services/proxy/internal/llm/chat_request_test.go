package llm

import (
	"errors"
	"strings"
	"testing"
)

func TestParseChatCompletionRequest_valid(t *testing.T) {
	body := `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}],"stream":false,"temperature":0.7}`
	req, err := ParseChatCompletionRequest(strings.NewReader(body))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if req.Model != "gpt-4" || len(req.Messages) != 1 {
		t.Fatalf("got %+v", req)
	}
	if req.Messages[0].Role != "user" || req.Messages[0].Content != "hi" {
		t.Fatalf("message: %+v", req.Messages[0])
	}
	if req.Stream {
		t.Fatal("expected stream false")
	}
	if req.Temperature == nil || *req.Temperature != 0.7 {
		t.Fatalf("temperature: %v", req.Temperature)
	}
}

func TestParseChatCompletionRequest_unknownFieldsIgnored(t *testing.T) {
	body := `{"model":"m","messages":[],"extra_field":true}`
	req, err := ParseChatCompletionRequest(strings.NewReader(body))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if req.Model != "m" {
		t.Fatalf("model: %q", req.Model)
	}
}

func TestParseChatCompletionRequest_invalidJSON(t *testing.T) {
	_, err := ParseChatCompletionRequest(strings.NewReader(`{invalid`))
	if !errors.Is(err, ErrInvalidJSON) {
		t.Fatalf("err: %v", err)
	}
}

func TestParseChatCompletionRequest_rootArray(t *testing.T) {
	_, err := ParseChatCompletionRequest(strings.NewReader(`[]`))
	if !errors.Is(err, ErrInvalidJSON) {
		t.Fatalf("err: %v", err)
	}
}

func TestParseChatCompletionRequest_messagesNotArray(t *testing.T) {
	_, err := ParseChatCompletionRequest(strings.NewReader(`{"model":"m","messages":"x"}`))
	if !errors.Is(err, ErrInvalidJSON) {
		t.Fatalf("err: %v", err)
	}
}

func TestParseChatCompletionRequest_messageNotObject(t *testing.T) {
	_, err := ParseChatCompletionRequest(strings.NewReader(`{"model":"m","messages":[1]}`))
	if !errors.Is(err, ErrInvalidJSON) {
		t.Fatalf("err: %v", err)
	}
}

func TestParseChatCompletionRequest_missingMessagesOK(t *testing.T) {
	req, err := ParseChatCompletionRequest(strings.NewReader(`{"model":"m"}`))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(req.Messages) != 0 {
		t.Fatalf("messages: %v", req.Messages)
	}
}

func TestParseChatCompletionRequest_emptyModelOK(t *testing.T) {
	req, err := ParseChatCompletionRequest(strings.NewReader(`{"messages":[]}`))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if req.Model != "" {
		t.Fatalf("model: %q", req.Model)
	}
}
