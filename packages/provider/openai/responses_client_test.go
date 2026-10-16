package openai

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestCreateResponsePropagatesUpstreamError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error":{"message":"boom"}}`))
	}))
	defer srv.Close()
	c := New(Config{APIKey: "k", BaseURL: srv.URL}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	if _, err := c.CreateResponse(context.Background(), responses.Request{Model: "gpt-4o"}, responses.CredentialOverride{}); err == nil {
		t.Fatal("upstream error must propagate")
	}
}

func TestCreateResponseRejectsMalformedBody(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"output":[{"id":"missing-type"}]}`))
	}))
	defer srv.Close()
	c := New(Config{APIKey: "k", BaseURL: srv.URL}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	if _, err := c.CreateResponse(context.Background(), responses.Request{Model: "gpt-4o"}, responses.CredentialOverride{}); err == nil {
		t.Fatal("malformed body must fail parsing")
	}
}
