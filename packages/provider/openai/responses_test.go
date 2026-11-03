package openai

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestCreateResponsePropagatesTenantCredentialAndParsesUsage(t *testing.T) {
	var gotKey string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotKey = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"resp_1","status":"completed","usage":{"input_tokens":2,"output_tokens":3,"total_tokens":5},"output":[]}`))
	}))
	defer srv.Close()
	c := New(Config{APIKey: "platform", BaseURL: srv.URL}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	out, err := c.CreateResponse(context.Background(), responses.Request{Model: "gpt-4o"}, responses.CredentialOverride{APIKey: "tenant-key"})
	if err != nil {
		t.Fatal(err)
	}
	if gotKey != "Bearer tenant-key" {
		t.Fatalf("auth=%q", gotKey)
	}
	if out.Usage == nil {
		t.Fatal("usage missing")
	}
	if out.Usage.TotalTokens != 5 {
		t.Fatalf("usage=%+v", out.Usage)
	}
}

func TestCreateResponseRejectsOversizedBody(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Test server returns a raw byte payload, not HTML: no XSS sink.
		_, _ = w.Write([]byte(strings.Repeat("x", responsesBodyLimit+1))) // nosemgrep: go.lang.security.audit.xss.no-direct-write-to-responsewriter.no-direct-write-to-responsewriter
	}))
	defer srv.Close()
	c := New(Config{APIKey: "k", BaseURL: srv.URL}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	if _, err := c.CreateResponse(context.Background(), responses.Request{Model: "gpt-4o"}, responses.CredentialOverride{}); err == nil || !strings.Contains(err.Error(), "exceeds") {
		t.Fatalf("err=%v", err)
	}
}

func TestCompleteResponsesRawWrapperAndStreamRejection(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"r","status":"completed","output":[]}`))
	}))
	defer srv.Close()
	c := New(Config{APIKey: "k", BaseURL: srv.URL}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	raw, err := c.CompleteResponses(context.Background(), responses.Request{Model: "gpt-4o"}, "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = raw.Body.Close() }()
	if raw.StatusCode != http.StatusOK {
		t.Fatalf("status=%d", raw.StatusCode)
	}
	if _, err := c.CreateResponse(context.Background(), responses.Request{Model: "gpt-4o", Stream: true}, responses.CredentialOverride{}); err == nil {
		t.Fatal("stream must be rejected")
	}
}
