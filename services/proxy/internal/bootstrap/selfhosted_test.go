package bootstrap

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/openaicompatible"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestWaitSelfHostedReady_SuccessAfterRetry(t *testing.T) {
	t.Parallel()
	var n int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/models" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		n++
		if n < 2 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	t.Cleanup(srv.Close)

	err := waitSelfHostedReady(context.Background(), srv.URL, config.SelfHostedConfig{
		ReadyTimeout: 2 * time.Second,
		ReadyPoll:    10 * time.Millisecond,
	}, logger.Discard("t"))
	if err != nil {
		t.Fatalf("err=%v", err)
	}
}

func TestWaitSelfHostedReady_Timeout(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	err := waitSelfHostedReady(context.Background(), srv.URL, config.SelfHostedConfig{
		ReadyTimeout: 40 * time.Millisecond,
		ReadyPoll:    10 * time.Millisecond,
	}, logger.Discard("t"))
	if err == nil || !strings.Contains(err.Error(), "readiness probe failed") {
		t.Fatalf("err=%v", err)
	}
}

func TestNewSelfHostedReadyChecker(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer k" {
			t.Fatalf("auth=%q", r.Header.Get("Authorization"))
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	check := newSelfHostedReadyChecker(srv.URL, "k")
	if err := check(context.Background()); err != nil {
		t.Fatalf("err=%v", err)
	}
}

func TestBuildProxyHealth_IncludesSelfHostedAdvisory(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		SelfHosted: config.SelfHostedConfig{
			Enabled: true,
			BaseURL: "http://127.0.0.1:9/v1",
		},
	}
	cfg.ApplyDefaults()
	h := buildProxyHealth(cfg, nil, nil, nil)
	if _, ok := h.AdvisoryCheckers["selfhosted_llm"]; !ok {
		t.Fatal("missing selfhosted_llm advisory")
	}
}

func TestBuildProviderRegistry_MockIgnoresSelfHosted(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		Environment: "development",
		LLMMode:     "mock",
		SelfHosted: config.SelfHostedConfig{
			Enabled: true,
			BaseURL: "http://127.0.0.1:9/v1",
			Models:  []string{"local-llama"},
		},
		ModelCapabilityOverlays: []provider.ModelCapability{{
			ModelID: "local-llama", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 8192, MaxOutputTokens: 1024,
			SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyUnknown,
		}},
	}
	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if _, err := reg.For("local-llama"); err == nil {
		t.Fatal("self-hosted must not register under mock")
	}
}

func TestBuildProviderRegistry_LiveSelfHostedOnly(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/models"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"data":[{"id":"local-llama"}]}`))
		default:
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
		}
	}))
	t.Cleanup(srv.Close)

	cfg := config.Config{
		LLMMode: "live",
		SelfHosted: config.SelfHostedConfig{
			Enabled:      true,
			BaseURL:      srv.URL + "/v1",
			Models:       []string{"local-llama"},
			ReadyTimeout: 2 * time.Second,
			ReadyPoll:    10 * time.Millisecond,
		},
		ModelCapabilityOverlays: []provider.ModelCapability{{
			ModelID: "local-llama", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 8192, MaxOutputTokens: 1024,
			SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyUnknown,
		}},
		ProviderBreakerFailures: 5,
		ProviderBreakerCoolDown: 30 * time.Second,
	}
	cfg.ApplyDefaults()

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	p, err := reg.For("local-llama")
	if err != nil {
		t.Fatalf("For: %v", err)
	}
	if p.Name() != openaicompatible.ProviderNameSelfHosted {
		t.Fatalf("provider=%q", p.Name())
	}
	if _, ok := reg.Capability("local-llama"); !ok {
		t.Fatal("Capability missing")
	}
}

func TestActiveExtraModels_SelfHostedUsesOpenAIOverlayFamily(t *testing.T) {
	t.Parallel()
	out, err := activeExtraModels(config.Config{
		SelfHosted: config.SelfHostedConfig{
			Enabled: true,
			Models:  []string{"local-a", "local-b"},
		},
	})
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if out["local-a"] != provider.CapabilityProviderOpenAI || out["local-b"] != provider.CapabilityProviderOpenAI {
		t.Fatalf("out=%v", out)
	}
}

func TestWaitSelfHostedReady_ContextCanceled(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := waitSelfHostedReady(ctx, srv.URL, config.SelfHostedConfig{
		ReadyTimeout: time.Second,
		ReadyPoll:    50 * time.Millisecond,
	}, logger.Discard("t"))
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("err=%v", err)
	}
}

func TestNewSelfHostedReadyChecker_Failure(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	check := newSelfHostedReadyChecker(srv.URL, "")
	if err := check(context.Background()); err == nil {
		t.Fatal("expected error")
	}
}

func TestBuildProviderRegistry_SelfHostedReadyFailure(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	cfg := config.Config{
		LLMMode: "live",
		SelfHosted: config.SelfHostedConfig{
			Enabled:      true,
			BaseURL:      srv.URL + "/v1",
			Models:       []string{"local-llama"},
			ReadyTimeout: 30 * time.Millisecond,
			ReadyPoll:    10 * time.Millisecond,
		},
		ModelCapabilityOverlays: []provider.ModelCapability{{
			ModelID: "local-llama", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 8192, MaxOutputTokens: 1024,
			SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyUnknown,
		}},
	}
	cfg.ApplyDefaults()
	_, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err == nil || !strings.Contains(err.Error(), "readiness") {
		t.Fatalf("err=%v", err)
	}
}

func TestAddVendorExtraIDs_Conflict(t *testing.T) {
	t.Parallel()
	dst := map[string]string{"shared": provider.CapabilityProviderOpenAI}
	err := addVendorExtraIDs(dst, provider.CapabilityProviderAnthropic, []string{"shared"})
	if err == nil || !strings.Contains(err.Error(), "claimed by both") {
		t.Fatalf("err=%v", err)
	}
}

func TestErrString(t *testing.T) {
	t.Parallel()
	if errString(nil) != "" {
		t.Fatal("nil")
	}
	if errString(errors.New("x")) != "x" {
		t.Fatal("err")
	}
}

func TestWaitSelfHostedReady_Defaults(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	// Zero timeouts exercise default branches then succeed immediately.
	err := waitSelfHostedReady(context.Background(), srv.URL, config.SelfHostedConfig{}, logger.Discard("t"))
	if err != nil {
		t.Fatalf("err=%v", err)
	}
}

func TestWaitSelfHostedReady_BlockedHandlerHonorsTimeout(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(5 * time.Second):
			w.WriteHeader(http.StatusOK)
		}
	}))
	t.Cleanup(srv.Close)
	start := time.Now()
	err := waitSelfHostedReady(context.Background(), srv.URL, config.SelfHostedConfig{
		ReadyTimeout: 80 * time.Millisecond,
		ReadyPoll:    20 * time.Millisecond,
	}, logger.Discard("t"))
	elapsed := time.Since(start)
	if err == nil {
		t.Fatal("expected timeout")
	}
	if elapsed > 500*time.Millisecond {
		t.Fatalf("elapsed=%s too long", elapsed)
	}
}

func TestWaitSelfHostedReady_PollCappedByTimeout(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	t.Cleanup(srv.Close)
	start := time.Now()
	err := waitSelfHostedReady(context.Background(), srv.URL, config.SelfHostedConfig{
		ReadyTimeout: 60 * time.Millisecond,
		ReadyPoll:    5 * time.Second, // must not extend past ReadyTimeout
	}, logger.Discard("t"))
	elapsed := time.Since(start)
	if err == nil {
		t.Fatal("expected timeout")
	}
	if !errors.Is(err, context.DeadlineExceeded) && !strings.Contains(err.Error(), "readiness probe failed") {
		t.Fatalf("err=%v", err)
	}
	if elapsed > 500*time.Millisecond {
		t.Fatalf("elapsed=%s; ReadyPoll must be capped", elapsed)
	}
}
