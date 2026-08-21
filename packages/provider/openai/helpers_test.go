package openai

import (
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
	if !provider.IsRetryableHTTPStatus(http.StatusTooManyRequests) {
		t.Fatal("429 should retry")
	}
	if provider.IsRetryableHTTPStatus(http.StatusBadRequest) {
		t.Fatal("400 should not retry")
	}
}

func TestOpenAI_ProviderErrorImplementsError(t *testing.T) {
	t.Parallel()
	var err error = &provider.ProviderError{StatusCode: 500, ProviderErrMsg: "fail"}
	if err.Error() == "" {
		t.Fatal("expected error string")
	}
}
