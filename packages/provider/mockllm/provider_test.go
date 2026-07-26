package mockllm

import (
	"context"
	"io"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func closeBody(t *testing.T, body io.Closer) {
	t.Helper()
	t.Cleanup(func() {
		if err := body.Close(); err != nil {
			t.Errorf("Body.Close: %v", err)
		}
	})
}

func TestUnit_CompleteReturnsOK(t *testing.T) {
	t.Parallel()

	var p Provider
	req := provider.Request{Model: "gpt-4o-mini"}

	resp, err := p.Complete(context.Background(), req)

	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	closeBody(t, resp.Body)
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if len(body) == 0 {
		t.Fatal("empty body")
	}
	if p.Name() != "mock" {
		t.Fatalf("name=%q", p.Name())
	}
	if len(p.SupportedModels()) == 0 {
		t.Fatal("expected models")
	}
}

func TestUnit_CompleteStreamReturnsSSE(t *testing.T) {
	t.Parallel()

	var p Provider
	req := provider.Request{Model: "gpt-4o", Stream: true}

	resp, err := p.Complete(context.Background(), req)

	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	closeBody(t, resp.Body)
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	got := string(body)
	if !strings.Contains(got, "data:") || !strings.Contains(got, "[DONE]") {
		t.Fatalf("expected SSE body, got %q", got)
	}
}
