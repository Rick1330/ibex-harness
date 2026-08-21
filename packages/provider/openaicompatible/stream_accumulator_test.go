package openaicompatible

import (
	"context"
	"strings"
	"testing"
	"time"
	"unicode/utf8"
)

func TestUnit_StreamAccumulator_Complete(t *testing.T) {
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

func TestUnit_StreamAccumulator_DoneSignalReached(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	finished := make(chan struct{})
	go func() {
		_, _, _ = acc.Wait(context.Background())
		close(finished)
	}()
	_, _ = acc.Write([]byte(`data: {"choices":[{"delta":{"content":"x"}}]}` + "\n\n"))
	select {
	case <-finished:
		t.Fatal("Wait returned before [DONE]")
	default:
	}
	_, _ = acc.Write([]byte("data: [DONE]\n\n"))
	select {
	case <-finished:
	case <-time.After(time.Second):
		t.Fatal("Wait did not unblock on [DONE]")
	}
}

func TestUnit_StreamAccumulator_ParseFailureDoesNotFailWrite(t *testing.T) {
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

func TestUnit_StreamAccumulator_SoftCap(t *testing.T) {
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
	if !utf8.ValidString(content) {
		t.Fatal("soft-cap truncation left invalid UTF-8")
	}
}

func TestUnit_StreamAccumulator_SoftCapUTF8Boundary(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	pad := strings.Repeat("a", MaxAccumulatedContentBytes-1)
	_, _ = acc.Write([]byte(`data: {"choices":[{"delta":{"content":"` + pad + `"}}]}` + "\n\n"))
	_, _ = acc.Write([]byte(`data: {"choices":[{"delta":{"content":"\u20ac"}}]}` + "\n\n"))
	_, _ = acc.Write([]byte("data: [DONE]\n\n"))
	content, _, err := acc.Wait(context.Background())
	if err != nil {
		t.Fatalf("Wait: %v", err)
	}
	if !utf8.ValidString(content) {
		t.Fatalf("invalid UTF-8 after rune-boundary soft cap: %q", content)
	}
	if strings.Contains(content, "€") {
		t.Fatal("expected multi-byte rune to be dropped at cap boundary")
	}
}

func TestUnit_StreamAccumulator_WaitTimeout(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	_, _, err := acc.Wait(ctx)
	if err == nil {
		t.Fatal("expected timeout")
	}
}

func TestUnit_StreamAccumulator_WriteAfterClosed(t *testing.T) {
	t.Parallel()
	acc := NewStreamAccumulator()
	acc.MarkClosed()
	n, err := acc.Write([]byte("data: ignored\n\n"))
	if err != nil || n == 0 {
		t.Fatalf("n=%d err=%v", n, err)
	}
}

