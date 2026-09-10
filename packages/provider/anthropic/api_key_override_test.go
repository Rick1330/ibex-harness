package anthropic

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"go.opentelemetry.io/otel/trace/noop"
)

func TestUnit_NewMessagesRequest_APIKeySelection(t *testing.T) {
	t.Parallel()
	client := New(Config{
		APIKey:  "cfg-key",
		BaseURL: "https://api.anthropic.com",
	}, logger.Discard("anthropic"), noop.NewTracerProvider().Tracer("test"), nil)

	overrideReq, err := client.newMessagesRequest(context.Background(), provider.UpstreamCall{
		URL:            "https://api.anthropic.com/v1/messages",
		Body:           []byte(`{}`),
		APIKeyOverride: "override-key",
	})
	if err != nil {
		t.Fatal(err)
	}
	if got := overrideReq.Header.Get("x-api-key"); got != "override-key" {
		t.Fatalf("override x-api-key=%q", got)
	}

	cfgReq, err := client.newMessagesRequest(context.Background(), provider.UpstreamCall{
		URL:  "https://api.anthropic.com/v1/messages",
		Body: []byte(`{}`),
	})
	if err != nil {
		t.Fatal(err)
	}
	if got := cfgReq.Header.Get("x-api-key"); got != "cfg-key" {
		t.Fatalf("cfg x-api-key=%q", got)
	}
}

func TestUnit_Complete_BaseURLOverride(t *testing.T) {
	t.Parallel()
	var hit atomic.Bool
	byo := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hit.Store(true)
		if r.URL.Path != "/v1/messages" {
			t.Fatalf("path=%q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{
			"id":"msg_1","type":"message","role":"assistant","model":"claude-sonnet-4-5",
			"content":[{"type":"text","text":"ok"}],
			"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}
		}`)
	}))
	t.Cleanup(byo.Close)
	platform := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("platform endpoint must not be used when BaseURLOverride is set")
	}))
	t.Cleanup(platform.Close)

	zero := 0
	client := New(Config{
		APIKey:     "cfg-key",
		BaseURL:    platform.URL,
		Timeout:    5 * time.Second,
		MaxRetries: &zero,
	}, logger.Discard("anthropic"), noop.NewTracerProvider().Tracer("test"), nil)

	_, err := client.Complete(context.Background(), provider.Request{
		Model:           modelClaudeSonnet45,
		Messages:        []provider.Message{{Role: "user", Content: "hi"}},
		BaseURLOverride: byo.URL,
		APIKeyOverride:  "byo-key",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !hit.Load() {
		t.Fatal("expected BYO endpoint hit")
	}
}
