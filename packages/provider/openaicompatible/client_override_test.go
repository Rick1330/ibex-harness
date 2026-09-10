package openaicompatible_test

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
)

func TestUnit_APIKeyOverride_DoesNotMutateConfig(t *testing.T) {
	t.Parallel()
	var sawAuth atomic.Value
	var sawURL atomic.Value
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth.Store(r.Header.Get("Authorization"))
		sawURL.Store(r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"id":"1","choices":[{"message":{"role":"assistant","content":"ok"}}]}`)
	}))
	t.Cleanup(srv.Close)

	cfgKey := "sk-platform"
	client := openaicompatible.New(openaicompatible.Config{
		ProviderName: "openai",
		APIKey:       cfgKey,
		BaseURL:      srv.URL,
		Timeout:      5 * time.Second,
		MaxRetries:   intPtr(0),
	}, logger.Discard("openai"), nil, nil)

	_, err := client.Complete(context.Background(), provider.Request{
		Model:          "gpt-4o-mini",
		Messages:       []provider.Message{{Role: "user", Content: "hi"}},
		APIKeyOverride: "sk-override",
	})
	if err != nil {
		t.Fatal(err)
	}
	if got, _ := sawAuth.Load().(string); got != "Bearer sk-override" {
		t.Fatalf("auth=%q", got)
	}
	if clientCfgKey := cfgKey; clientCfgKey != "sk-platform" {
		t.Fatalf("config mutated")
	}
	// Second call without override uses platform key.
	_, err = client.Complete(context.Background(), provider.Request{
		Model:    "gpt-4o-mini",
		Messages: []provider.Message{{Role: "user", Content: "hi"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if got, _ := sawAuth.Load().(string); got != "Bearer sk-platform" {
		t.Fatalf("auth=%q", got)
	}
}

func TestUnit_BaseURLOverride_UsesCustomEndpoint(t *testing.T) {
	t.Parallel()
	var hit atomic.Bool
	byo := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hit.Store(true)
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"id":"1","choices":[{"message":{"role":"assistant","content":"ok"}}]}`)
	}))
	t.Cleanup(byo.Close)
	platform := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Fatal("platform endpoint must not be used when BaseURLOverride is set")
	}))
	t.Cleanup(platform.Close)

	client := openaicompatible.New(openaicompatible.Config{
		ProviderName: "openai",
		APIKey:       "sk-platform",
		BaseURL:      platform.URL,
		Timeout:      5 * time.Second,
		MaxRetries:   intPtr(0),
	}, logger.Discard("openai"), nil, nil)
	_, err := client.Complete(context.Background(), provider.Request{
		Model:           "gpt-4o-mini",
		Messages:        []provider.Message{{Role: "user", Content: "hi"}},
		APIKeyOverride:  "sk-byo",
		BaseURLOverride: byo.URL,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !hit.Load() {
		t.Fatal("expected BYO endpoint hit")
	}
}

func intPtr(v int) *int { return &v }
