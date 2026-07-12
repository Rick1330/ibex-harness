package openai

import (
	"net/http"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestRetryAfterHeader_seconds(t *testing.T) {
	t.Parallel()
	if got := RetryAfterHeader("30"); got != 30*time.Second {
		t.Fatalf("got %v", got)
	}
}

func TestRetryAfterHeader_empty(t *testing.T) {
	t.Parallel()
	if got := RetryAfterHeader(""); got != 0 {
		t.Fatalf("got %v", got)
	}
}

func TestIsRetryableStatus(t *testing.T) {
	t.Parallel()
	if !isRetryableStatus(http.StatusTooManyRequests) {
		t.Fatal("429 should retry")
	}
	if isRetryableStatus(http.StatusBadRequest) {
		t.Fatal("400 should not retry")
	}
}

func TestReadProviderError_setsRetryAfter(t *testing.T) {
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

func TestExtractOpenAIErrorMessage_fallback(t *testing.T) {
	t.Parallel()
	if msg := extractOpenAIErrorMessage([]byte(`not json`)); msg != "upstream provider error" {
		t.Fatalf("msg: %q", msg)
	}
}

func TestProviderError_implementsError(t *testing.T) {
	t.Parallel()
	var err error = &provider.ProviderError{StatusCode: 500, ProviderErrMsg: "fail"}
	if err.Error() == "" {
		t.Fatal("expected error string")
	}
}
