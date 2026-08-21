package anthropic

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestRetryAfterHeader(t *testing.T) {
	t.Parallel()
	if RetryAfterHeader("") != 0 {
		t.Fatal("empty")
	}
	if RetryAfterHeader("2") != 2*time.Second {
		t.Fatal("seconds")
	}
}

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
	if isRetryableTransport(context.Canceled) {
		t.Fatal("canceled")
	}
	if !isRetryableTransport(&net.OpError{Op: "dial", Err: errors.New("refused")}) {
		t.Fatal("op error")
	}
}

func TestRequest_ToolRoleRejected(t *testing.T) {
	t.Parallel()
	_, err := marshalAnthropicRequestBody(provider.Request{
		Model: modelClaudeSonnet45,
		Messages: []provider.Message{
			{Role: "user", Content: "hi"},
			{Role: "tool", Content: "{}"},
		},
	}, 1024)
	var pe *provider.ProviderError
	if !errors.As(err, &pe) || pe.StatusCode != http.StatusBadRequest {
		t.Fatalf("err=%v", err)
	}
}

func TestRequest_EmptyNonSystemRejected(t *testing.T) {
	t.Parallel()
	_, err := marshalAnthropicRequestBody(provider.Request{
		Model:    modelClaudeSonnet45,
		Messages: []provider.Message{{Role: "system", Content: "only"}},
	}, 1024)
	if err == nil {
		t.Fatal("expected error")
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
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(body), `"finish_reason":"length"`) {
		t.Fatalf("body=%s", body)
	}
}
