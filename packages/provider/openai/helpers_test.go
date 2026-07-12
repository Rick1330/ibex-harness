package openai

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestOpenAI_RetryAfterHeaderSeconds(t *testing.T) {
	t.Parallel()
	if got := RetryAfterHeader("30"); got != 30*time.Second {
		t.Fatalf("got %v", got)
	}
}

func TestOpenAI_RetryAfterHeaderEmpty(t *testing.T) {
	t.Parallel()
	if got := RetryAfterHeader(""); got != 0 {
		t.Fatalf("got %v", got)
	}
}

func TestOpenAI_IsRetryableStatus(t *testing.T) {
	t.Parallel()
	if !isRetryableStatus(http.StatusTooManyRequests) {
		t.Fatal("429 should retry")
	}
	if isRetryableStatus(http.StatusBadRequest) {
		t.Fatal("400 should not retry")
	}
}

func TestOpenAI_ReadProviderErrorSetsRetryAfter(t *testing.T) {
	t.Parallel()
	resp := &http.Response{
		StatusCode: http.StatusTooManyRequests,
		Header:     http.Header{"Retry-After": []string{"15"}},
		Body:       http.NoBody,
	}
	pe := readProviderError("openai", resp)
	if pe.RetryAfter != 15*time.Second {
		t.Fatalf("retry after: %v", pe.RetryAfter)
	}
}

func TestOpenAI_ExtractErrorMessageFallback(t *testing.T) {
	t.Parallel()
	if msg := extractOpenAIErrorMessage([]byte(`not json`)); msg != "upstream provider error" {
		t.Fatalf("msg: %q", msg)
	}
}

func TestOpenAI_ProviderErrorImplementsError(t *testing.T) {
	t.Parallel()
	var err error = &provider.ProviderError{StatusCode: 500, ProviderErrMsg: "fail"}
	if err.Error() == "" {
		t.Fatal("expected error string")
	}
}

func TestOpenAI_WaitBeforeRetryPrefersHeaderRetryAfter(t *testing.T) {
	t.Parallel()
	client := testClient(t, "http://example.com", "k", nil)
	start := time.Now()
	err := client.waitBeforeRetry(context.Background(), 1, &provider.ProviderError{
		StatusCode:   http.StatusTooManyRequests,
		RetryAfter:   10 * time.Millisecond,
		ProviderBody: []byte(`{"error":{"retry_after":60}}`),
	})
	if err != nil {
		t.Fatalf("waitBeforeRetry: %v", err)
	}
	if elapsed := time.Since(start); elapsed > 50*time.Millisecond {
		t.Fatalf("expected header Retry-After delay, got %v", elapsed)
	}
}
