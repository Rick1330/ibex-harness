package provider

import (
	"strings"
	"testing"
)

func TestUnit_ProviderError_Error(t *testing.T) {
	t.Parallel()
	err := &ProviderError{
		ProviderName:   "openai",
		StatusCode:     429,
		ProviderBody:   []byte(`{"error":{"message":"secret details"}}`),
		ProviderErrMsg: "rate limit exceeded",
	}

	got := err.Error()
	want := "provider openai returned 429: rate limit exceeded"

	if got != want {
		t.Fatalf("Error() = %q, want %q", got, want)
	}

	if strings.Contains(got, "secret details") {
		t.Fatal("Error() must not include raw provider body")
	}
}
