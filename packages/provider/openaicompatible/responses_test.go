package openaicompatible

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider/responses"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestCompleteResponsesUsesOverrideAndCredential(t *testing.T) {
	var gotPath, gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotAuth = r.URL.Path, r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"r","status":"completed","output":[]}`))
	}))
	defer srv.Close()
	c := New(Config{ProviderName: "test", BaseURL: "http://invalid", MaxRetries: zeroRetries()}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	out, err := c.CompleteResponses(context.Background(), responses.Request{Model: "gpt-4o"}, "tenant", srv.URL+"/v1")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = out.Body.Close() }()
	if _, err := io.ReadAll(out.Body); err != nil {
		t.Fatal(err)
	}
	if gotPath != "/v1/responses" || gotAuth != "Bearer tenant" {
		t.Fatalf("path=%q auth=%q", gotPath, gotAuth)
	}
}

func TestCompleteResponsesRejectsInvalidRequest(t *testing.T) {
	c := New(Config{ProviderName: "test", BaseURL: "http://invalid", MaxRetries: zeroRetries()}, logger.Discard("test"), telemetry.NoopTracer("test"), nil)
	if _, err := c.CompleteResponses(context.Background(), responses.Request{}, "", ""); err == nil || !strings.Contains(err.Error(), "model") {
		t.Fatalf("err=%v", err)
	}
}
