package http

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

type captureLLMProvider struct {
	last provider.Request
}

func (c *captureLLMProvider) Complete(_ context.Context, req provider.Request) (provider.Response, error) {
	c.last = req
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(`{"ok":true}`)),
	}, nil
}

func (c *captureLLMProvider) Name() string { return "capture" }

func (c *captureLLMProvider) SupportedModels() []string { return []string{"gpt-4o"} }

func TestUnit_ApplyDirectiveInjection_SystemFirst(t *testing.T) {
	t.Parallel()
	msgs := []provider.Message{{Role: "user", Content: "hi"}}
	ctx := WithResolvedDirective(context.Background(), directive.Resolved{
		Content: "Be safe.", InjectionMode: "system_first",
	})
	out := applyDirectiveInjection(ctx, msgs)
	if len(out) != 2 {
		t.Fatalf("len=%d", len(out))
	}
	if out[0].Role != "system" || out[0].Content != "Be safe." {
		t.Fatalf("injected: %+v", out[0])
	}
	if out[1].Content != "hi" {
		t.Fatalf("user: %+v", out[1])
	}
}

func TestUnit_ApplyDirectiveInjection_MissingOrEmpty(t *testing.T) {
	t.Parallel()
	msgs := []provider.Message{{Role: "user", Content: "hi"}}
	unchanged := applyDirectiveInjection(context.Background(), msgs)
	if len(unchanged) != 1 || unchanged[0].Content != "hi" {
		t.Fatalf("missing ctx: %+v", unchanged)
	}
	ctx := WithResolvedDirective(context.Background(), directive.Resolved{})
	empty := applyDirectiveInjection(ctx, msgs)
	if len(empty) != 1 || empty[0].Content != "hi" {
		t.Fatalf("empty content: %+v", empty)
	}
}

func TestUnit_ForwardChatCompletion_InjectsBeforeComplete(t *testing.T) {
	t.Parallel()
	cap := &captureLLMProvider{}
	parsed := &llm.ChatCompletionRequest{
		Model: "gpt-4o",
		Messages: []llm.Message{
			{Role: "system", Content: "client system"},
			{Role: "user", Content: "hello"},
		},
	}
	ctx := WithResolvedDirective(context.Background(), directive.Resolved{
		Content: "org directive", InjectionMode: "system_append", VersionID: uuid.New(),
	})
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{log: logger.Discard("proxy")}
	h.forwardChatCompletion(chatForwardParams{
		w: rec, r: req, parsed: parsed, prov: cap,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	if len(cap.last.Messages) != 3 {
		t.Fatalf("messages=%+v", cap.last.Messages)
	}
	if cap.last.Messages[0].Content != "client system" {
		t.Fatalf("first=%+v", cap.last.Messages[0])
	}
	if cap.last.Messages[1].Role != "system" || cap.last.Messages[1].Content != "org directive" {
		t.Fatalf("appended=%+v", cap.last.Messages[1])
	}
	if cap.last.Messages[2].Content != "hello" {
		t.Fatalf("user=%+v", cap.last.Messages[2])
	}
}

func TestUnit_ForwardChatCompletion_NoDirectiveUnchanged(t *testing.T) {
	t.Parallel()
	cap := &captureLLMProvider{}
	parsed := &llm.ChatCompletionRequest{
		Model:    "gpt-4o",
		Messages: []llm.Message{{Role: "user", Content: "hello"}},
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	rec := httptest.NewRecorder()
	h := chatCompletionHandler{log: logger.Discard("proxy")}
	h.forwardChatCompletion(chatForwardParams{
		w: rec, r: req, parsed: parsed, prov: cap,
	})
	if len(cap.last.Messages) != 1 || cap.last.Messages[0].Content != "hello" {
		t.Fatalf("messages=%+v", cap.last.Messages)
	}
}
