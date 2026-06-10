//go:build integration

package proxy_test

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
)

const (
	minimalChatBody         = `{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}`
	rateLimitBurstRPM       = int64(5)
	timingParityThresholdMs = 50
	defaultRevocationSLAMs  = 300
)

func revocationSLA(t *testing.T) time.Duration {
	t.Helper()
	if v := os.Getenv("REVOCATION_SLA_MS"); v != "" {
		ms, err := strconv.Atoi(v)
		if err != nil {
			t.Fatalf("REVOCATION_SLA_MS: %v", err)
		}
		return time.Duration(ms) * time.Millisecond
	}
	return time.Duration(defaultRevocationSLAMs) * time.Millisecond
}

func assertSecurityErrorEnvelope(t *testing.T, resp *http.Response, body, secret string) {
	t.Helper()
	assertErrorStatus(t, resp, body)
	assertJSONContentType(t, resp, body)
	envelope := parseErrorEnvelope(t, body)
	assertRequestIDCorrelation(t, resp, envelope)
	assertNoSecretInBody(t, body, secret)
}

func assertErrorStatus(t *testing.T, resp *http.Response, body string) {
	t.Helper()
	if resp.StatusCode < 400 {
		t.Fatalf("expected error status, got %d body=%s", resp.StatusCode, body)
	}
}

func assertJSONContentType(t *testing.T, resp *http.Response, body string) {
	t.Helper()
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Fatalf("Content-Type want application/json got %q body=%s", ct, body)
	}
}

func parseErrorEnvelope(t *testing.T, body string) apierror.Response {
	t.Helper()
	var envelope apierror.Response
	if err := json.Unmarshal([]byte(body), &envelope); err != nil {
		t.Fatalf("json unmarshal: %v body=%s", err, body)
	}
	if envelope.Error.Code == "" || envelope.Error.Message == "" {
		t.Fatalf("missing error fields body=%s", body)
	}
	if envelope.Error.RequestID == "" || envelope.Error.Timestamp.IsZero() {
		t.Fatalf("missing request_id or timestamp body=%s", body)
	}
	return envelope
}

func assertRequestIDCorrelation(t *testing.T, resp *http.Response, envelope apierror.Response) {
	t.Helper()
	hdrID := resp.Header.Get("X-Request-ID")
	if hdrID == "" {
		t.Fatal("missing X-Request-ID response header")
	}
	if hdrID != envelope.Error.RequestID {
		t.Fatalf("request_id mismatch header=%q body=%q", hdrID, envelope.Error.RequestID)
	}
}

func assertNoSecretInBody(t *testing.T, body, secret string) {
	t.Helper()
	if secret != "" && strings.Contains(body, secret) {
		t.Fatalf("response body leaks secret token")
	}
}

func assertNoTokenLeak(t *testing.T, body, secret string) {
	t.Helper()
	assertNoSecretInBody(t, body, secret)
	if strings.Contains(strings.ToLower(body), "bearer ") {
		t.Fatalf("response body contains bearer prefix: %s", body)
	}
}

func securityEnv(t *testing.T) securityTestEnv {
	t.Helper()
	return setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: 60})
}

func rateLimitEnv(t *testing.T) securityTestEnv {
	t.Helper()
	return setupSecurityTestEnv(t, proxyServerOpts{defaultRPM: rateLimitBurstRPM})
}

func orgAProbeOpts(env securityTestEnv) authProbeOpts {
	return authProbeOpts{srvURL: env.proxy.URL, bearer: env.orgA.Token, agentID: env.orgA.AgentID}
}

type probeExpect struct {
	status int
	code   string
}

func requireProbe(t *testing.T, opts authProbeOpts, exp probeExpect, secret string) {
	t.Helper()
	resp, body := authProbeGET(t, opts)
	defer resp.Body.Close()
	if resp.StatusCode != exp.status {
		t.Fatalf("status=%d want=%d body=%s", resp.StatusCode, exp.status, body)
	}
	if exp.code != "" && !strings.Contains(body, exp.code) {
		t.Fatalf("body=%s want code %q", body, exp.code)
	}
	if exp.status >= 400 {
		assertSecurityErrorEnvelope(t, resp, body, secret)
	}
}

func requireProbeOK(t *testing.T, opts authProbeOpts) {
	t.Helper()
	resp, _ := authProbeGET(t, opts)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status=%d", resp.StatusCode)
	}
}

func exhaustOrgARateLimit(t *testing.T, env securityTestEnv) {
	t.Helper()
	opts := orgAProbeOpts(env)
	for i := 0; i < int(rateLimitBurstRPM)+1; i++ {
		resp, _ := authProbeGET(t, opts)
		resp.Body.Close()
	}
}

func lastBurstProbe(t *testing.T, env securityTestEnv) (*http.Response, string) {
	t.Helper()
	opts := orgAProbeOpts(env)
	var resp *http.Response
	var body string
	for i := 0; i < int(rateLimitBurstRPM)+1; i++ {
		resp, body = authProbeGET(t, opts)
	}
	return resp, body
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

func parseHeaderInt(t *testing.T, hdr, label string) int64 {
	t.Helper()
	if hdr == "" {
		t.Fatalf("missing %s header", label)
	}
	v, err := strconv.ParseInt(hdr, 10, 64)
	if err != nil {
		t.Fatalf("%s not int: %q", label, hdr)
	}
	return v
}

func parseRetryAfter(t *testing.T, hdr string) int {
	t.Helper()
	return int(parseHeaderInt(t, hdr, "Retry-After"))
}

func parseResetUnix(t *testing.T, hdr string) int64 {
	t.Helper()
	return parseHeaderInt(t, hdr, "X-RateLimit-Reset")
}
