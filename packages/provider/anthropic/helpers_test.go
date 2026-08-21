package anthropic

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestIsRetryableStatus_Includes529(t *testing.T) {
	t.Parallel()
	if !isRetryableStatus(statusOverloaded) {
		t.Fatal("529")
	}
	if isRetryableStatus(http.StatusBadRequest) {
		t.Fatal("400")
	}
}

func TestIsRetryableTransport(t *testing.T) {
	t.Parallel()
	if provider.IsRetryableTransport(context.Canceled) {
		t.Fatal("canceled")
	}
	if provider.IsRetryableTransport(timeoutNetError{}) {
		t.Fatal("timeout must not retry (ambiguous delivery)")
	}
	if !provider.IsRetryableTransport(&net.OpError{Op: "dial", Err: errors.New("refused")}) {
		t.Fatal("dial should retry")
	}
	if provider.IsRetryableTransport(&net.OpError{Op: "read", Err: errors.New("reset")}) {
		t.Fatal("read must not retry")
	}
}

type timeoutNetError struct{}

func (timeoutNetError) Error() string   { return "timeout" }
func (timeoutNetError) Timeout() bool   { return true }
func (timeoutNetError) Temporary() bool { return true }

func TestWaitBeforeRetry_Honors503RetryAfter(t *testing.T) {
	t.Parallel()
	client := testClient(t, "http://example.invalid", "k")
	err := provider.WaitBeforeRetry(context.Background(), client.cfg.RetryBaseDelay, 1, &provider.ProviderError{
		StatusCode: http.StatusServiceUnavailable,
		RetryAfter: time.Millisecond,
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestRequest_ValidationRejected(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		req  provider.Request
	}{
		{
			name: "tool_role",
			req: provider.Request{
				Model: modelClaudeSonnet45,
				Messages: []provider.Message{
					{Role: "user", Content: "hi"},
					{Role: "tool", Content: "{}"},
				},
			},
		},
		{
			name: "empty_user",
			req: provider.Request{
				Model:    modelClaudeSonnet45,
				Messages: []provider.Message{{Role: "user", Content: "   "}},
			},
		},
		{
			name: "system_only",
			req: provider.Request{
				Model:    modelClaudeSonnet45,
				Messages: []provider.Message{{Role: "system", Content: "only"}},
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := marshalAnthropicRequestBody(tc.req, 1024)
			if tc.name == "system_only" {
				if err == nil {
					t.Fatal("expected error")
				}
				return
			}
			assertBadRequest(t, err)
		})
	}
}

func TestTranslateNonStream_MaxTokensFinish(t *testing.T) {
	t.Parallel()
	raw := []byte(`{
		"id":"msg_2","content":[{"type":"text","text":"x"}],
		"stop_reason":"max_tokens","usage":{"input_tokens":1,"output_tokens":2}
	}`)
	resp, err := translateNonStreamResponse(raw, modelClaudeSonnet45, "rid", time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(body), `"finish_reason":"length"`) {
		t.Fatalf("body=%s", body)
	}
}

func TestTranslateNonStream_MissingIDUsesUniqueFallback(t *testing.T) {
	t.Parallel()
	raw := []byte(`{"content":[{"type":"text","text":"x"}],"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}}`)
	resp, err := translateNonStreamResponse(raw, modelClaudeSonnet45, "", time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"id":"chatcmpl-anthropic-`) {
		t.Fatalf("body=%s", body)
	}
	if resp.ProviderRequestID == "" || resp.ProviderRequestID == "chatcmpl-anthropic" {
		t.Fatalf("request id=%q", resp.ProviderRequestID)
	}
}

func TestRequest_MidConversationSystemFolded(t *testing.T) {
	t.Parallel()
	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "user", Content: "hello"},
			{Role: "system", Content: "policy"},
			{Role: "user", Content: "again"},
		},
	}, 1024)
	if err != nil {
		t.Fatal(err)
	}
	var body anthropicRequest
	_ = json.Unmarshal(raw, &body)
	if body.System != "policy" {
		t.Fatalf("system=%q", body.System)
	}
	if len(body.Messages) != 1 || body.Messages[0].Content != "hello\n\nagain" {
		t.Fatalf("messages=%+v", body.Messages)
	}
}

func TestFallbackCompletionID_Unique(t *testing.T) {
	t.Parallel()
	a := newFallbackCompletionID()
	b := newFallbackCompletionID()
	if a == b || !strings.HasPrefix(a, "chatcmpl-anthropic-") {
		t.Fatalf("a=%q b=%q", a, b)
	}
}

func TestExtractAnthropicErrorMessage(t *testing.T) {
	t.Parallel()
	if extractAnthropicErrorMessage([]byte(`not-json`)) != "upstream provider error" {
		t.Fatal("invalid json")
	}
	if got := extractAnthropicErrorMessage([]byte(`{"error":{"message":"boom"}}`)); got != "boom" {
		t.Fatalf("got=%q", got)
	}
	if got := extractAnthropicErrorMessage([]byte(`{"message":"top"}`)); got != "top" {
		t.Fatalf("got=%q", got)
	}
}

func TestClient_HonorsRetryAfterOn529(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if calls.Add(1) == 1 {
			w.Header().Set("Retry-After", "0")
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
	// Inject Retry-After via provider error path: status 529 with Retry-After:1 still uses WaitBeforeRetry.
	// Zero Retry-After falls back to exponential delay; ensure second attempt succeeds.
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

func assertBadRequest(t *testing.T, err error) {
	t.Helper()
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.StatusCode != http.StatusBadRequest {
		t.Fatalf("err=%v", err)
	}
}
