package anthropic

import (
	"encoding/json"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestStreamTranslate_TextAndDone(t *testing.T) {
	t.Parallel()
	anth := anthropicSSEFixture(
		`event: message_start`,
		`data: {"type":"message_start","message":{"id":"msg_s","model":"claude-sonnet-4-5"}}`,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}`,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"!"}}`,
		`event: message_delta`,
		`data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}`,
		`event: message_stop`,
		`data: {"type":"message_stop"}`,
	)
	out := mustTranslateAll(t, anth, modelClaudeSonnet45, "fallback-id")
	assertContainsAll(t, out, `"content":"Hi"`, `"content":"!"`, `"finish_reason":"stop"`, "data: [DONE]")
	assertChunkID(t, out, "msg_s")
	assertChunksParse(t, out)
}

func TestStreamTranslate_MidStreamOverloaded(t *testing.T) {
	t.Parallel()
	anth := anthropicSSEFixture(
		`event: message_start`,
		`data: {"type":"message_start","message":{"id":"msg_s"}}`,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"partial"}}`,
		`event: error`,
		`data: {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}`,
	)
	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(anth)), modelClaudeSonnet45, "")
	defer func() { _ = pipe.Close() }()
	_, err := io.ReadAll(pipe)
	if err == nil {
		t.Fatal("expected overload error")
	}
	if !strings.Contains(err.Error(), "Overloaded") && !strings.Contains(err.Error(), "529") {
		t.Fatalf("err=%v", err)
	}
}

func TestStreamTranslate_IgnoresNonTextDelta(t *testing.T) {
	t.Parallel()
	anth := anthropicSSEFixture(
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{}"}}`,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"ok"}}`,
		`event: message_stop`,
		`data: {"type":"message_stop"}`,
	)
	out := mustTranslateAll(t, anth, modelClaudeSonnet45, "id")
	assertContainsAll(t, out, `"content":"ok"`)
	if strings.Contains(out, "partial_json") {
		t.Fatal("leaked tool json into OpenAI stream")
	}
}

func TestStreamTranslate_PingAndCommentKeepalive(t *testing.T) {
	t.Parallel()
	anth := ": keepalive\nevent: ping\ndata: {\"type\":\"ping\"}\n\n" + anthropicSSEFixture(
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"x"}}`,
		`event: message_stop`,
		`data: {"type":"message_stop"}`,
	)
	out := mustTranslateAll(t, anth, modelClaudeSonnet45, "id")
	assertContainsAll(t, out, ": keepalive", ": ping", `"content":"x"`)
}

func TestStreamTranslate_EventSizeLimit(t *testing.T) {
	t.Parallel()
	chunk := strings.Repeat("a", 256*1024)
	var b strings.Builder
	b.WriteString("event: content_block_delta\n")
	for i := 0; i < 10; i++ {
		b.WriteString("data: ")
		b.WriteString(chunk)
		b.WriteByte('\n')
	}
	b.WriteByte('\n')
	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(b.String())), modelClaudeSonnet45, "id")
	defer func() { _ = pipe.Close() }()
	_, err := io.ReadAll(pipe)
	if err == nil {
		t.Fatal("expected size limit error")
	}
}

func TestStreamTranslate_CloseUnblocksProducer(t *testing.T) {
	t.Parallel()
	pr, pw := io.Pipe()
	go func() {
		defer func() { _ = pw.Close() }()
		_, _ = io.WriteString(pw, "event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"id\":\"m\"}}\n\n")
		for i := 0; i < 100000; i++ {
			if _, err := io.WriteString(pw, "event: content_block_delta\ndata: {\"delta\":{\"type\":\"text_delta\",\"text\":\"x\"}}\n\n"); err != nil {
				return
			}
		}
	}()
	pipe := newStreamTranslatePipe(pr, modelClaudeSonnet45, "id")
	buf := make([]byte, 64)
	_, _ = pipe.Read(buf)
	done := make(chan struct{})
	go func() {
		_ = pipe.Close()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Close hung")
	}
}

func TestStreamTranslate_RateLimitError(t *testing.T) {
	t.Parallel()
	anth := anthropicSSEFixture(
		`event: error`,
		`data: {"type":"error","error":{"type":"rate_limit_error","message":"slow down"}}`,
	)
	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(anth)), modelClaudeSonnet45, "id")
	defer func() { _ = pipe.Close() }()
	_, err := io.ReadAll(pipe)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.StatusCode != 429 {
		t.Fatalf("err=%v", err)
	}
}

func anthropicSSEFixture(lines ...string) string {
	var b strings.Builder
	for _, line := range lines {
		b.WriteString(line)
		b.WriteByte('\n')
		if strings.HasPrefix(line, "data:") {
			b.WriteByte('\n')
		}
	}
	return b.String()
}

func mustTranslateAll(t *testing.T, anth, model, id string) string {
	t.Helper()
	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(anth)), model, id)
	defer func() { _ = pipe.Close() }()
	out, err := io.ReadAll(pipe)
	if err != nil {
		t.Fatal(err)
	}
	return string(out)
}

func assertChunkID(t *testing.T, out, wantID string) {
	t.Helper()
	var chunk openAIStreamChunk
	for _, block := range strings.Split(out, "\n\n") {
		if !strings.HasPrefix(block, "data: {") {
			continue
		}
		_ = json.Unmarshal([]byte(strings.TrimPrefix(block, "data: ")), &chunk)
		if chunk.ID == wantID {
			return
		}
	}
	t.Fatalf("missing id %q in %s", wantID, out)
}

func assertChunksParse(t *testing.T, out string) {
	t.Helper()
	for _, block := range strings.Split(out, "\n\n") {
		payload, ok := openAIChunkPayload(block)
		if !ok {
			continue
		}
		var chunk openAIStreamChunk
		if err := json.Unmarshal([]byte(payload), &chunk); err != nil {
			t.Fatalf("chunk json: %v (%s)", err, block)
		}
		if chunk.Object != openAIChunkObject {
			t.Fatalf("object=%q", chunk.Object)
		}
	}
}

func openAIChunkPayload(block string) (string, bool) {
	block = strings.TrimSpace(block)
	if block == "" || block == "data: [DONE]" || strings.HasPrefix(block, ":") {
		return "", false
	}
	if !strings.HasPrefix(block, "data: ") {
		return "", false
	}
	return strings.TrimPrefix(block, "data: "), true
}
