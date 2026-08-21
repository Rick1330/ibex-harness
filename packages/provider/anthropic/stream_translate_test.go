package anthropic

import (
	"encoding/json"
	"io"
	"strings"
	"testing"
	"time"
)

func TestStreamTranslate_TextAndDone(t *testing.T) {
	t.Parallel()
	anth := strings.Join([]string{
		`event: message_start`,
		`data: {"type":"message_start","message":{"id":"msg_s","model":"claude-sonnet-4-5"}}`,
		``,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}`,
		``,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"!"}}`,
		``,
		`event: message_delta`,
		`data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}`,
		``,
		`event: message_stop`,
		`data: {"type":"message_stop"}`,
		``,
	}, "\n")

	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(anth)), modelClaudeSonnet45, "")
	defer pipe.Close()
	out, err := io.ReadAll(pipe)
	if err != nil {
		t.Fatal(err)
	}
	s := string(out)
	if !strings.Contains(s, `"role":"assistant"`) {
		t.Fatalf("missing role: %s", s)
	}
	if !strings.Contains(s, `"content":"Hi"`) || !strings.Contains(s, `"content":"!"`) {
		t.Fatalf("missing content: %s", s)
	}
	if !strings.Contains(s, `"finish_reason":"stop"`) {
		t.Fatalf("missing finish: %s", s)
	}
	if !strings.Contains(s, "data: [DONE]") {
		t.Fatalf("missing DONE: %s", s)
	}
	// Ensure OpenAI-shaped chunks parse.
	for _, block := range strings.Split(s, "\n\n") {
		block = strings.TrimSpace(block)
		if block == "" || block == "data: [DONE]" {
			continue
		}
		if !strings.HasPrefix(block, "data: ") {
			continue
		}
		payload := strings.TrimPrefix(block, "data: ")
		var chunk openAIStreamChunk
		if err := json.Unmarshal([]byte(payload), &chunk); err != nil {
			t.Fatalf("chunk json: %v (%s)", err, payload)
		}
		if chunk.Object != "chat.completion.chunk" {
			t.Fatalf("object=%q", chunk.Object)
		}
	}
}

func TestStreamTranslate_MidStreamOverloaded(t *testing.T) {
	t.Parallel()
	anth := strings.Join([]string{
		`event: message_start`,
		`data: {"type":"message_start","message":{"id":"msg_s"}}`,
		``,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"partial"}}`,
		``,
		`event: error`,
		`data: {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}`,
		``,
	}, "\n")

	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(anth)), modelClaudeSonnet45, "")
	defer pipe.Close()
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
	anth := strings.Join([]string{
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{}"}}`,
		``,
		`event: content_block_delta`,
		`data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"ok"}}`,
		``,
		`event: message_stop`,
		`data: {"type":"message_stop"}`,
		``,
	}, "\n")
	pipe := newStreamTranslatePipe(io.NopCloser(strings.NewReader(anth)), modelClaudeSonnet45, "id")
	defer pipe.Close()
	out, err := io.ReadAll(pipe)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(out), `"content":"ok"`) {
		t.Fatalf("out=%s", out)
	}
	if strings.Contains(string(out), "partial_json") {
		t.Fatal("leaked tool json into OpenAI stream")
	}
}

func TestStreamTranslate_EventSizeLimit(t *testing.T) {
	t.Parallel()
	// Multiple data: lines under the Scanner line cap that assemble past maxSSEEventBytes.
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
	defer pipe.Close()
	_, err := io.ReadAll(pipe)
	if err == nil {
		t.Fatal("expected size limit error")
	}
}

func TestStreamTranslate_CloseUnblocksProducer(t *testing.T) {
	t.Parallel()
	pr, pw := io.Pipe()
	// Never-ending Anthropic stream of text deltas.
	go func() {
		defer pw.Close()
		_, _ = io.WriteString(pw, "event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"id\":\"m\"}}\n\n")
		for i := 0; i < 100000; i++ {
			if _, err := io.WriteString(pw, "event: content_block_delta\ndata: {\"delta\":{\"type\":\"text_delta\",\"text\":\"x\"}}\n\n"); err != nil {
				return
			}
		}
	}()
	pipe := newStreamTranslatePipe(pr, modelClaudeSonnet45, "id")
	// Read a little, then close — must not deadlock the producer.
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

