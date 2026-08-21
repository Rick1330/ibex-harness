package anthropic

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestConfig_ApplyDefaultsBranches(t *testing.T) {
	t.Parallel()
	neg := -3
	c := Config{MaxRetries: &neg, RetryBaseDelay: -1, DefaultTokens: -1}
	c.ApplyDefaults()
	assertDefaultsApplied(t, c)
	var bare Config
	if bare.maxRetries() != defaultMaxRetries {
		t.Fatal("nil maxRetries")
	}
}

func assertDefaultsApplied(t *testing.T, c Config) {
	t.Helper()
	requireField(t, c.BaseURL != "", "base url")
	requireField(t, c.APIVersion != "", "api version")
	requireField(t, c.Timeout > 0, "timeout")
	requireField(t, c.StreamTimeout > 0, "stream timeout")
	requireField(t, c.MaxRetries != nil && *c.MaxRetries == 0, "max retries")
	requireField(t, c.RetryBaseDelay == defaultRetryBaseDelay, "retry delay")
	requireField(t, c.DefaultTokens == defaultMaxTokens, "tokens")
}

func requireField(t *testing.T, ok bool, name string) {
	t.Helper()
	if !ok {
		t.Fatal(name)
	}
}

func TestNoopMetrics(t *testing.T) {
	t.Parallel()
	var m Metrics = noopMetrics{}
	m.IncProviderRequest("anthropic", "2xx")
	m.IncProviderRetry("anthropic")
}

func TestClient_RejectsNonEventStream(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(srv.Close)
	_, err := testClient(t, srv.URL, "k").Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Stream:   true,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || !strings.Contains(pe.ProviderErrMsg, "event-stream") {
		t.Fatalf("err=%v", err)
	}
}

func TestClient_MarshalError(t *testing.T) {
	t.Parallel()
	_, err := testClient(t, "http://example.invalid", "k").Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "assistant", Content: "x"}},
	})
	if err == nil {
		t.Fatal("expected validation error")
	}
}

func TestClient_UnknownRole(t *testing.T) {
	t.Parallel()
	_, err := marshalAnthropicRequestBody(provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "a"}, {Role: "developer", Content: "b"}},
	}, 10)
	assertBadRequest(t, err)
}

func TestConcatAndMapStop(t *testing.T) {
	t.Parallel()
	if concatTextBlocks([]anthropicContent{{Type: "tool_use", Text: "x"}, {Type: "text", Text: "y"}}) != "y" {
		t.Fatal("concat")
	}
	if mapStopReason("stop_sequence") != "stop" || mapStopReason("weird") != "stop" {
		t.Fatal("map")
	}
}

func TestTruncateErrMsg(t *testing.T) {
	t.Parallel()
	if truncateErrMsg("short") != "short" {
		t.Fatal("short")
	}
	long := strings.Repeat("a", 600)
	if got := truncateErrMsg(long); len(got) != 512 {
		t.Fatalf("len=%d", len(got))
	}
}

func TestTranslateInvalidJSON(t *testing.T) {
	t.Parallel()
	_, err := translateNonStreamResponse([]byte(`{`), modelClaudeSonnet45, "id", time.Millisecond)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestStream_InventFinishWhenMissing(t *testing.T) {
	t.Parallel()
	anth := anthropicSSEFixture(
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"solo"}}`,
	)
	out := mustTranslateAll(t, anth, modelClaudeSonnet45, "")
	assertContainsAll(t, out, `"content":"solo"`, `"finish_reason":"stop"`, "data: [DONE]")
	if !strings.Contains(out, "chatcmpl-anthropic-") {
		t.Fatalf("expected unique fallback id: %s", out)
	}
}

func TestStream_MalformedDeltasIgnored(t *testing.T) {
	t.Parallel()
	anth := anthropicSSEFixture(
		`event: content_block_delta`,
		`data: not-json`,
		`event: message_delta`,
		`data: not-json`,
		`event: message_start`,
		`data: not-json`,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"ok"}}`,
		`event: message_stop`,
		`data: {"type":"message_stop"}`,
	)
	out := mustTranslateAll(t, anth, modelClaudeSonnet45, "id")
	assertContainsAll(t, out, `"content":"ok"`)
}

func TestNew_NilDeps(t *testing.T) {
	t.Parallel()
	c := New(Config{APIKey: "k"}, logger.Discard("a"), nil, nil)
	if c.tracer == nil {
		t.Fatal("tracer")
	}
	if c.metrics == nil || c.clients.Stream == nil {
		t.Fatal("metrics/stream")
	}
}

func TestAcceptJSON_ReadError(t *testing.T) {
	t.Parallel()
	pr, pw := io.Pipe()
	_ = pw.CloseWithError(io.ErrUnexpectedEOF)
	out := (&Client{cfg: Config{}}).acceptJSONBody(&http.Response{Body: pr}, modelClaudeSonnet45, "id", time.Millisecond)
	if out.Err == nil {
		t.Fatal("expected read error")
	}
}

func TestClient_TransportDialFailureNoRetryOnTimeoutSemantics(t *testing.T) {
	t.Parallel()
	zero := 0
	client := New(Config{
		APIKey:         "k",
		BaseURL:        "http://127.0.0.1:1",
		MaxRetries:     &zero,
		RetryBaseDelay: time.Millisecond,
		Timeout:        50 * time.Millisecond,
	}, logger.Discard("a"), nil, nil)
	_, err := client.Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err == nil {
		t.Fatal("expected dial error")
	}
}

func TestClient_ReadProviderErrorMessage(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Retry-After", "1")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"error":{"type":"rate_limit_error","message":"rl"}}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	client := New(Config{
		APIKey: "k", BaseURL: srv.URL, MaxRetries: &zero, RetryBaseDelay: time.Millisecond,
	}, logger.Discard("a"), nil, nil)
	_, err := client.Complete(context.Background(), provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	var pe *provider.ProviderError
	if !errors.As(err, &pe) {
		t.Fatalf("err=%v", err)
	}
	if pe.StatusCode != 429 {
		t.Fatalf("status=%d", pe.StatusCode)
	}
	if pe.ProviderErrMsg != "rl" {
		t.Fatalf("msg=%q", pe.ProviderErrMsg)
	}
}

func TestFoldEmptyMidSystem(t *testing.T) {
	t.Parallel()
	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "system", Content: "lead"},
			{Role: "user", Content: "u"},
			{Role: "system", Content: "  "},
			{Role: "assistant", Content: "a"},
		},
	}, 10)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), `"system":"lead"`) {
		t.Fatalf("%s", raw)
	}
}

func TestSSE_KeepaliveAndUnknownFields(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		anth string
		want []string
	}{
		{
			name: "unknown_fields",
			anth: "id: 1\nretry: 1000\n" + anthropicSSEFixture(
				`event: content_block_delta`,
				`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"z"}}`,
				`event: message_stop`,
				`data: {"type":"message_stop"}`,
			),
			want: []string{`"content":"z"`},
		},
		{
			name: "empty_comment",
			anth: ":\n" + anthropicSSEFixture(
				`event: content_block_delta`,
				`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"k"}}`,
				`event: message_stop`,
				`data: {"type":"message_stop"}`,
			),
			want: []string{": keepalive", `"content":"k"`},
		},
		{
			name: "empty_text_delta",
			anth: anthropicSSEFixture(
				`event: content_block_delta`,
				`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":""}}`,
				`event: content_block_delta`,
				`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"y"}}`,
				`event: message_stop`,
				`data: {"type":"message_stop"}`,
			),
			want: []string{`"content":"y"`},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			out := mustTranslateAll(t, tc.anth, modelClaudeSonnet45, "id")
			assertContainsAll(t, out, tc.want...)
		})
	}
}

func TestExtractAnthropicErrorMessage_EmptyPayload(t *testing.T) {
	t.Parallel()
	if extractAnthropicErrorMessage([]byte(`{}`)) != "upstream provider error" {
		t.Fatal("empty")
	}
	long := `{"error":{"message":"` + strings.Repeat("m", 600) + `"}}`
	if len(extractAnthropicErrorMessage([]byte(long))) != 512 {
		t.Fatal("truncate")
	}
}

func TestTranslateNonStream_UsesRequestModel(t *testing.T) {
	t.Parallel()
	raw := []byte(`{"content":[{"type":"text","text":"x"}],"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}}`)
	resp, err := translateNonStreamResponse(raw, "claude-custom", "rid", time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `"model":"claude-custom"`) {
		t.Fatalf("%s", body)
	}
}

func TestCoalesceEmptySecond(t *testing.T) {
	t.Parallel()
	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "user", Content: "a"},
			{Role: "user", Content: ""},
			{Role: "assistant", Content: "b"},
		},
	}, 10)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), `"a"`) {
		t.Fatalf("%s", raw)
	}
}

func TestCoalesceEmptyThenContent(t *testing.T) {
	t.Parallel()
	raw, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "user", Content: ""},
			{Role: "user", Content: "b"},
		},
	}, 10)
	if err != nil {
		t.Fatal(err)
	}
	var body anthropicRequest
	_ = json.Unmarshal(raw, &body)
	if len(body.Messages) != 1 || body.Messages[0].Content != "b" {
		t.Fatalf("%+v", body.Messages)
	}
}

func TestCoalesceTurnsNil(t *testing.T) {
	t.Parallel()
	if coalesceTurns(nil) != nil {
		t.Fatal("nil")
	}
}
