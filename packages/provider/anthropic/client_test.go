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
	raw := mustMarshalRequest(t, provider.Request{Model: modelClaudeSonnet45, Messages: msgs}, 4096)
	assertMessagesUnchanged(t, msgs, orig)
	body := mustDecodeAnthropicRequest(t, raw)
	if body.System != "be helpful\n\nbe brief" || body.MaxTokens != 4096 {
		t.Fatalf("system=%q max_tokens=%d", body.System, body.MaxTokens)
	}
	if len(body.Messages) != 1 || body.Messages[0].Role != "user" {
		t.Fatalf("messages=%+v", body.Messages)
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
	assertBadRequest(t, err)

	raw := mustMarshalRequest(t, provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "user", Content: "a"},
			{Role: "user", Content: "b"},
			{Role: "assistant", Content: "c"},
		},
	}, 1024)
	body := mustDecodeAnthropicRequest(t, raw)
	if len(body.Messages) != 2 || body.Messages[0].Content != "a\n\nb" {
		t.Fatalf("coalesce=%+v", body.Messages)
	}
}

func TestRequest_DenyPassthroughOverrides(t *testing.T) {
	t.Parallel()
	raw := mustMarshalRequest(t, provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
		PassthroughFields: map[string]any{
			"model":  "evil",
			"tools":  []any{map[string]any{"name": "x"}},
			"top_p":  0.5,
			"system": "override",
		},
	}, 1024)
	var merged map[string]any
	_ = json.Unmarshal(raw, &merged)
	if merged["model"] != modelClaudeSonnet45 || merged["top_p"] != 0.5 {
		t.Fatalf("merged=%v", merged)
	}
	if _, ok := merged["tools"]; ok {
		t.Fatal("tools passthrough must be blocked")
	}
	if merged["system"] == "override" {
		t.Fatal("system override allowed")
	}
}

func TestNonStream_Translate(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertAnthropicHeaders(t, r)
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

	resp := mustComplete(t, testClient(t, srv.URL, "test-key"), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	defer func() { _ = resp.Body.Close() }()
	body := mustReadAll(t, resp.Body)
	assertContainsAll(t, body, `"object":"chat.completion"`, `"finish_reason":"stop"`)
	if resp.ProviderRequestID != "req_123" || resp.Usage == nil || resp.Usage.TotalTokens != 4 {
		t.Fatalf("id=%q usage=%+v", resp.ProviderRequestID, resp.Usage)
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

	resp := mustComplete(t, testClient(t, srv.URL, "test-key"), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
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

func TestClient_NoRetryAfterStreamStarts(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.Header().Set("Content-Type", "text/event-stream")
		flusher, _ := w.(http.Flusher)
		_, _ = io.WriteString(w, "event: error\ndata: {\"type\":\"error\",\"error\":{\"type\":\"overloaded_error\",\"message\":\"Overloaded\"}}\n\n")
		if flusher != nil {
			flusher.Flush()
		}
	}))
	t.Cleanup(srv.Close)

	client := testClient(t, srv.URL, "test-key")
	resp, err := client.Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Stream:   true,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()
	_, _ = io.Copy(io.Discard, resp.Body)
	if calls.Load() != 1 {
		t.Fatalf("calls=%d want 1 (no retry after stream body)", calls.Load())
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

func mustMarshalRequest(t *testing.T, req provider.Request, defaults int) []byte {
	t.Helper()
	raw, err := marshalAnthropicRequestBody(req, defaults)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func mustDecodeAnthropicRequest(t *testing.T, raw []byte) anthropicRequest {
	t.Helper()
	var body anthropicRequest
	if err := json.Unmarshal(raw, &body); err != nil {
		t.Fatal(err)
	}
	return body
}

func assertMessagesUnchanged(t *testing.T, msgs, orig []provider.Message) {
	t.Helper()
	for i := range msgs {
		if msgs[i] != orig[i] {
			t.Fatalf("mutated messages[%d]", i)
		}
	}
}

func assertAnthropicHeaders(t *testing.T, r *http.Request) {
	t.Helper()
	if r.Header.Get("x-api-key") != "test-key" || r.Header.Get("anthropic-version") != defaultAPIVersion || r.URL.Path != "/v1/messages" {
		t.Fatalf("headers/path unexpected: key=%q ver=%q path=%q", r.Header.Get("x-api-key"), r.Header.Get("anthropic-version"), r.URL.Path)
	}
}

func mustComplete(t *testing.T, client *Client, req provider.Request) provider.Response {
	t.Helper()
	resp, err := client.Complete(context.Background(), req)
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

func mustReadAll(t *testing.T, r io.Reader) string {
	t.Helper()
	b, err := io.ReadAll(r)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func assertContainsAll(t *testing.T, body string, needles ...string) {
	t.Helper()
	for _, n := range needles {
		if !strings.Contains(body, n) {
			t.Fatalf("missing %q in %s", n, body)
		}
	}
}
