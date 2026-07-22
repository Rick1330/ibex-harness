package openai

import (
	"context"
	"strings"
	"testing"
	"time"
)

func TestStreaming_AccumulatorComplete(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	sse := "" +
		"data: {\"choices\":[{\"delta\":{\"content\":\"Hel\"}}]}\n\n" +
		"data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}]}\n\n" +
		"data: {\"choices\":[{\"delta\":{\"content\":\"!\"}}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":3,\"total_tokens\":4}}\n\n" +
		"data: [DONE]\n\n"
	if _, err := acc.Write([]byte(sse)); err != nil {
		t.Fatalf("Write: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	content, usage, err := acc.Wait(ctx)
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if content != "Hello!" {
		t.Fatalf("content=%q", content)
	}
	if usage == nil || usage.TotalTokens != 4 {
		t.Fatalf("usage=%v", usage)
	}
	if !acc.Complete() {
		t.Fatal("expected Complete")
	}
}

func TestStreaming_DoneSignalReached(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	done := make(chan struct{})
	go func() {
		_, _, _ = acc.Wait(context.Background())
		close(done)
	}()
	time.Sleep(20 * time.Millisecond)
	select {
	case <-done:
		t.Fatal("Wait returned before [DONE]")
	default:
	}
	_, _ = acc.Write([]byte("data: [DONE]\n\n"))
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("Wait did not unblock on [DONE]")
	}
}

func TestStreamAccumulator_ParseFailureDoesNotFailWrite(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	n, err := acc.Write([]byte("data: {not-json}\n\ndata: [DONE]\n\n"))
	if err != nil || n == 0 {
		t.Fatalf("Write n=%d err=%v", n, err)
	}
	if !acc.Complete() {
		t.Fatal("expected Complete after DONE despite bad JSON")
	}
}

func TestStreamAccumulator_SoftCap(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	chunk := strings.Repeat("x", 4096)
	payload := []byte(`data: {"choices":[{"delta":{"content":"` + chunk + `"}}]}` + "\n\n")
	for i := 0; i < (MaxAccumulatedContentBytes/4096)+2; i++ {
		_, _ = acc.Write(payload)
	}
	_, _ = acc.Write([]byte("data: [DONE]\n\n"))
	content, _, err := acc.Wait(context.Background())
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if len(content) > MaxAccumulatedContentBytes {
		t.Fatalf("content len %d exceeds cap", len(content))
	}
}

func TestStreamAccumulator_MarkClosed(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	_, _ = acc.Write([]byte(`data: {"choices":[{"delta":{"content":"hi"}}]}` + "\n\n"))
	acc.MarkClosed()
	content, usage, err := acc.Wait(context.Background())
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if content != "hi" {
		t.Fatalf("content=%q", content)
	}
	if usage != nil {
		t.Fatalf("unexpected usage %#v", usage)
	}
	if acc.Complete() {
		t.Fatal("MarkClosed should not set Complete")
	}
}
