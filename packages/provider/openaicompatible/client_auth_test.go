package openaicompatible

import (
	"bytes"
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
)

func TestClient_NonStreaming_Success_OmitEmptyAuth(t *testing.T) {
	t.Parallel()
	var sawAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)

	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		BaseURL:      srv.URL,
		Timeout:      5 * time.Second,
		MaxRetries:   &zero,
		ExtraModels:  []string{"local-model"},
		AuthMode:     AuthBearerOmitEmpty,
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)

	if c.Name() != ProviderNameSelfHosted {
		t.Fatalf("Name=%q", c.Name())
	}
	models := c.SupportedModels()
	if len(models) != 1 || models[0] != "local-model" {
		t.Fatalf("SupportedModels=%v", models)
	}

	resp, err := c.Complete(context.Background(), provider.Request{
		Model: "local-model", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "ok") {
		t.Fatalf("body=%s", body)
	}
	if sawAuth != "" {
		t.Fatalf("expected no Authorization, got %q", sawAuth)
	}
}

func TestClient_BearerWhenKeySet(t *testing.T) {
	t.Parallel()
	var sawAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		APIKey:       "secret",
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if sawAuth != "Bearer secret" {
		t.Fatalf("auth=%q", sawAuth)
	}
}

func TestClient_AlwaysAuthMode(t *testing.T) {
	t.Parallel()
	var sawAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	zero := 0
	c := New(Config{
		ProviderName:  ProviderNameOpenAI,
		APIKey:        "k",
		BaseURL:       srv.URL,
		MaxRetries:    &zero,
		AuthMode:      AuthBearerAlways,
		BuiltInModels: []string{"gpt-4o"},
	}, logger.Discard("t"), telemetry.NoopTracer("t"), nil)
	_, err := c.Complete(context.Background(), provider.Request{
		Model: "gpt-4o", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if sawAuth != "Bearer k" {
		t.Fatalf("auth=%q", sawAuth)
	}
}

func TestClient_APIKeyNotInLogs(t *testing.T) {
	t.Parallel()
	var buf bytes.Buffer
	log, err := logger.New(logger.Config{Service: "t", Level: slog.LevelDebug, Writer: &buf})
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	t.Cleanup(srv.Close)
	secret := "sk-never-log-me"
	zero := 0
	c := New(Config{
		ProviderName: ProviderNameSelfHosted,
		APIKey:       secret,
		BaseURL:      srv.URL,
		MaxRetries:   &zero,
		AuthMode:     AuthBearerOmitEmpty,
		ExtraModels:  []string{"m"},
	}, log, telemetry.NoopTracer("t"), nil)
	_, err = c.Complete(context.Background(), provider.Request{
		Model: "m", Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(buf.String(), secret) {
		t.Fatal("secret leaked")
	}
}
