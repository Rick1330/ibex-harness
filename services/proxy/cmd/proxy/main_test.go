package main

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
)

func TestRun_InvalidConfigReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "not-valid")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRateLimitSliderConfig(t *testing.T) {
	t.Parallel()
	orgID := uuid.MustParse("00000000-0000-0000-0000-000000000001")
	otherOrg := uuid.MustParse("00000000-0000-0000-0000-000000000002")
	cfg := config.Config{
		RateLimit: config.RateLimitConfig{
			DefaultRPM:   120,
			OrgOverrides: map[uuid.UUID]int{orgID: 30, otherOrg: 45},
		},
	}
	got := rateLimitSliderConfig(cfg)
	if got.DefaultRPM != 120 {
		t.Fatalf("DefaultRPM = %d, want 120", got.DefaultRPM)
	}
	if got.OrgOverrides[orgID] != 30 {
		t.Fatalf("org override = %d, want 30", got.OrgOverrides[orgID])
	}
	if got.OrgOverrides[otherOrg] != 45 {
		t.Fatalf("other org override = %d, want 45", got.OrgOverrides[otherOrg])
	}
	if len(got.OrgOverrides) != 2 {
		t.Fatalf("overrides: %+v", got.OrgOverrides)
	}
}

func TestSetupRateLimiter_NoRedis(t *testing.T) {
	log := logger.Discard("proxy")
	client, limiter, err := setupRateLimiter(config.Config{}, log)
	if err != nil {
		t.Fatalf("setupRateLimiter: %v", err)
	}
	if client != nil {
		t.Fatal("expected nil redis client")
	}
	if limiter == nil {
		t.Fatal("expected noop limiter")
	}
	result, err := limiter.Check(context.Background(), uuid.Nil, uuid.Nil)
	if err != nil || !result.Allowed {
		t.Fatalf("noop limiter check: result=%+v err=%v", result, err)
	}
}

func TestSetupRateLimiter_WithMiniredis(t *testing.T) {
	mr := miniredis.RunT(t)
	log := logger.Discard("proxy")
	cfg := config.Config{RedisURL: "redis://" + mr.Addr() + "/0"}
	client, limiter, err := setupRateLimiter(cfg, log)
	if err != nil {
		t.Fatalf("setupRateLimiter: %v", err)
	}
	t.Cleanup(func() { _ = client.Close() })
	if client == nil || limiter == nil {
		t.Fatal("expected redis client and limiter")
	}
}

func TestSetupRateLimiter_InvalidURL(t *testing.T) {
	log := logger.Discard("proxy")
	_, _, err := setupRateLimiter(config.Config{RedisURL: "not-a-redis-url"}, log)
	if err == nil {
		t.Fatal("expected error for invalid redis URL")
	}
}

func TestNewHTTPServer(t *testing.T) {
	t.Parallel()
	cfg := config.Config{Port: "8080"}
	cfg.ApplyDefaults()
	providerReg, err := provider.NewRegistry()
	if err != nil {
		t.Fatal(err)
	}
	srv := newHTTPServer(proxyhttp.RouterDeps{
		Config: cfg, Logger: logger.Discard("proxy"), Metrics: ibexmetrics.NewProxy("proxy"),
		Limiter: ratelimit.Noop(), Health: &healthcheck.Server{},
		ProviderRegistry: providerReg,
	})
	if srv.Addr != ":8080" {
		t.Fatalf("addr: %s", srv.Addr)
	}
	if srv.Handler == nil || srv.ReadHeaderTimeout != 5*time.Second {
		t.Fatalf("server: %+v", srv)
	}
}

func TestRun_InvalidLoggerLevelReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_LOG_LEVEL", "not-a-level")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_InvalidOTELSampleRatioReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("OTEL_SAMPLE_RATIO", "2")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_InvalidRedisURLReturns1(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("REDIS_URL", "not-a-redis-url")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}

func TestRun_ProviderRegistryInitFailureReturns1(t *testing.T) {
	orig := providerRegistryInit
	t.Cleanup(func() { providerRegistryInit = orig })
	providerRegistryInit = func(...provider.Provider) (*provider.Registry, error) {
		return nil, errors.New("registry init failed")
	}
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("REDIS_URL", "")
	t.Setenv("IBEX_AUTH_GRPC_ADDR", "")
	if got := run(nil); got != 1 {
		t.Fatalf("run() = %d, want 1", got)
	}
}
