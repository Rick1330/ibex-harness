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
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth.Store(r.Header.Get("Authorization"))
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

func intPtr(v int) *int { return &v }
