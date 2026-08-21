package anthropic

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace/noop"
)

func testClient(t *testing.T, baseURL, key string) *Client {
	t.Helper()
	return New(Config{
		APIKey:         key,
		BaseURL:        baseURL,
		MaxRetries:     intPtr(3),
		RetryBaseDelay: time.Millisecond,
	}, logger.Discard("anthropic"), noop.NewTracerProvider().Tracer("test"), nil)
}

func TestRequest_SystemExtractionNoMutation(t *testing.T) {
	t.Parallel()
	msgs := []provider.Message{
		{Role: "system", Content: "be helpful"},
		{Role: "system", Content: "be brief"},
		{Role: "user", Content: "hi"},
	}
	orig := append([]provider.Message(nil), msgs...)
	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: msgs,
	}, 4096)
	if err != nil {
		t.Fatal(err)
	}
	for i := range msgs {
		if msgs[i] != orig[i] {
			t.Fatalf("mutated messages[%d]", i)
		}
	}
	var body anthropicRequest
	if err := json.Unmarshal(raw, &body); err != nil {
		t.Fatal(err)
	}
	if body.System != "be helpful\n\nbe brief" {
		t.Fatalf("system=%q", body.System)
	}
	if len(body.Messages) != 1 || body.Messages[0].Role != "user" {
		t.Fatalf("messages=%+v", body.Messages)
	}
	if body.MaxTokens != 4096 {
		t.Fatalf("max_tokens=%d", body.MaxTokens)
	}
}

func TestRequest_CoalesceAndRejectAssistantFirst(t *testing.T) {
	t.Parallel()
	_, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "assistant", Content: "hello"},
			{Role: "user", Content: "hi"},
		},
	}, 1024)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.StatusCode != http.StatusBadRequest {
		t.Fatalf("err=%v", err)
	}

	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "user", Content: "a"},
			{Role: "user", Content: "b"},
			{Role: "assistant", Content: "c"},
		},
	}, 1024)
	if err != nil {
		t.Fatal(err)
	}
	var body anthropicRequest
	_ = json.Unmarshal(raw, &body)
	if len(body.Messages) != 2 || body.Messages[0].Content != "a\n\nb" {
		t.Fatalf("coalesce=%+v", body.Messages)
	}
}

func TestRequest_DenyPassthroughOverrides(t *testing.T) {
	t.Parallel()
	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{
			"model":  "evil",
			"tools":  []any{map[string]any{"name": "x"}},
			"top_p":  0.5,
			"system": "override",
		},
	}, 1024)
	if err != nil {
		t.Fatal(err)
	}
	var merged map[string]any
	_ = json.Unmarshal(raw, &merged)
	if merged["model"] != modelClaudeSonnet45 {
		t.Fatalf("model overridden: %v", merged["model"])
	}
	if _, ok := merged["system"]; ok && merged["system"] == "override" {
		t.Fatal("system override allowed")
	}
	if _, ok := merged["tools"]; ok {
		t.Fatal("tools passthrough must be blocked")
	}
	if merged["top_p"] != 0.5 {
		t.Fatalf("top_p missing: %v", merged["top_p"])
	}
}

func TestNonStream_Translate(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("x-api-key") != "test-key" {
			t.Errorf("x-api-key=%q", r.Header.Get("x-api-key"))
		}
		if r.Header.Get("anthropic-version") != defaultAPIVersion {
			t.Errorf("version=%q", r.Header.Get("anthropic-version"))
		}
		if r.URL.Path != "/v1/messages" {
			t.Errorf("path=%q", r.URL.Path)
		}
		w.Header().Set("request-id", "req_123")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"id":"msg_1","type":"message","role":"assistant",
			"content":[{"type":"text","text":"hello"}],
			"model":"claude-sonnet-4-5","stop_reason":"end_turn",
			"usage":{"input_tokens":3,"output_tokens":1}
		}`))
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key")
	resp, err := client.Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"object":"chat.completion"`) {
		t.Fatalf("body=%s", body)
	}
	if !strings.Contains(string(body), `"finish_reason":"stop"`) {
		t.Fatalf("finish_reason missing: %s", body)
	}
	if resp.ProviderRequestID != "req_123" {
		t.Fatalf("request id=%q", resp.ProviderRequestID)
	}
	if resp.Usage == nil || resp.Usage.TotalTokens != 4 {
		t.Fatalf("usage=%+v", resp.Usage)
	}
}

func TestClient_Retry_on529(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if calls.Add(1) < 2 {
			w.WriteHeader(statusOverloaded)
			_, _ = w.Write([]byte(`{"error":{"type":"overloaded_error","message":"Overloaded"}}`))
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"id":"msg_1","content":[{"type":"text","text":"ok"}],
			"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}
		}`))
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key")
	resp, err := client.Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	_ = resp.Body.Close()
	if calls.Load() != 2 {
		t.Fatalf("calls=%d", calls.Load())
	}
}

func TestClient_NoRetry_On400(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":{"type":"invalid_request_error","message":"bad"}}`))
	}))
	t.Cleanup(srv.Close)

	_, err := testClient(t, srv.URL, "test-key").Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.StatusCode != 400 {
		t.Fatalf("err=%v", err)
	}
	if calls.Load() != 1 {
		t.Fatalf("calls=%d", calls.Load())
	}
	if strings.Contains(pe.Error(), "test-key") {
		t.Fatal("api key leaked in error")
	}
}

func TestSupportedModels_Extra(t *testing.T) {
	t.Parallel()
	c := New(Config{APIKey: "k", ExtraModels: []string{"claude-custom"}}, logger.Discard("a"), nil, nil)
	models := c.SupportedModels()
	found := false
	for _, m := range models {
		if m == "claude-custom" {
			found = true
		}
	}
	if !found {
		t.Fatalf("models=%v", models)
	}
}

func TestMapStopReason(t *testing.T) {
	t.Parallel()
	if mapStopReason("max_tokens") != "length" {
		t.Fatal("max_tokens")
	}
	if mapStopReason("end_turn") != "stop" {
		t.Fatal("end_turn")
	}
}
