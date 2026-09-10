package anthropic

import (
	"context"
	"testing"

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
