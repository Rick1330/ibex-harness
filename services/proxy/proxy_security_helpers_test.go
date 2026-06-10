//go:build integration

package proxy_test

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

const minimalChatBody = `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`

func assertSecurityErrorEnvelope(t *testing.T, resp *http.Response, body, secret string) {
	t.Helper()
	if resp.StatusCode < 400 {
		t.Fatalf("expected error status, got %d body=%s", resp.StatusCode, body)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Fatalf("Content-Type want application/json got %q body=%s", ct, body)
	}
	var envelope apierror.Response
	if err := json.Unmarshal([]byte(body), &envelope); err != nil {
		t.Fatalf("json unmarshal: %v body=%s", err, body)
	}
	if envelope.Error.Code == "" {
		t.Fatalf("missing error.code body=%s", body)
	}
	if envelope.Error.Message == "" {
		t.Fatalf("missing error.message body=%s", body)
	}
	if envelope.Error.RequestID == "" {
		t.Fatalf("missing error.request_id body=%s", body)
	}
	if envelope.Error.Timestamp.IsZero() {
		t.Fatalf("missing error.timestamp body=%s", body)
	}
	hdrID := resp.Header.Get("X-Request-ID")
	if hdrID == "" {
		t.Fatal("missing X-Request-ID response header")
	}
	if hdrID != envelope.Error.RequestID {
		t.Fatalf("request_id mismatch header=%q body=%q", hdrID, envelope.Error.RequestID)
	}
	if secret != "" && strings.Contains(body, secret) {
		t.Fatalf("response body leaks secret token")
	}
}

func assertNoTokenLeak(t *testing.T, body, secret string) {
	t.Helper()
	if secret != "" && strings.Contains(body, secret) {
		t.Fatalf("response body leaks bearer token")
	}
	if strings.Contains(strings.ToLower(body), "bearer ") {
		t.Fatalf("response body contains bearer prefix: %s", body)
	}
}

func percentileMs(durations []time.Duration, p float64) time.Duration {
	if len(durations) == 0 {
		return 0
	}
	sorted := make([]time.Duration, len(durations))
	copy(sorted, durations)
	for i := 0; i < len(sorted); i++ {
		for j := i + 1; j < len(sorted); j++ {
			if sorted[j] < sorted[i] {
				sorted[i], sorted[j] = sorted[j], sorted[i]
			}
		}
	}
	idx := int(float64(len(sorted)-1) * p)
	return sorted[idx]
}

func parseIntHeader(t *testing.T, hdr string) int {
	t.Helper()
	if hdr == "" {
		t.Fatal("missing header value")
	}
	v, err := strconv.Atoi(hdr)
	if err != nil {
		t.Fatalf("header not int: %q", hdr)
	}
	return v
}

func parseRetryAfter(t *testing.T, hdr string) int {
	t.Helper()
	if hdr == "" {
		t.Fatal("missing Retry-After header")
	}
	v, err := strconv.Atoi(hdr)
	if err != nil {
		t.Fatalf("Retry-After not int: %q", hdr)
	}
	return v
}

func parseResetUnix(t *testing.T, hdr string) int64 {
	t.Helper()
	if hdr == "" {
		t.Fatal("missing X-RateLimit-Reset header")
	}
	v, err := strconv.ParseInt(hdr, 10, 64)
	if err != nil {
		t.Fatalf("X-RateLimit-Reset not int: %q", hdr)
	}
	return v
}
