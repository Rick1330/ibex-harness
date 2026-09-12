package bootstrap

import (
	"bytes"
	"context"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_BuildModelPolicyRuntime_NilPostgresPassthrough(t *testing.T) {
	t.Parallel()
	base := mustTestRegistry(t)
	var buf bytes.Buffer
	log, err := logger.New(logger.Config{Service: "bootstrap-mp", Level: slog.LevelWarn, Writer: &buf})
	if err != nil {
		t.Fatal(err)
	}
	reg := ibexmetrics.NewProxy("mp-passthrough-test")
	cache, resolver, defaults, err := buildModelPolicyRuntime(nil, base, log, reg)
	if err != nil {
		t.Fatal(err)
	}
	if cache != nil {
		t.Fatal("expected nil cache without postgres")
	}
	assertPassthroughResolver(t, resolver)
	assertNoopDefaults(t, defaults)
	if !strings.Contains(buf.String(), "model policy passthrough: org model policies disabled") {
		t.Fatalf("expected passthrough warn log, got %q", buf.String())
	}
	if !strings.Contains(buf.String(), "POSTGRES_DSN unset or db handle nil") {
		t.Fatalf("expected reason in warn log, got %q", buf.String())
	}
	assertModelPolicyEnabledGauge(t, reg, 0)
}

func TestUnit_StartModelPolicySubscriber_SkippedWithoutDeps(t *testing.T) {
	t.Parallel()
	sub, cancel, err := startModelPolicySubscriber(nil, nil, nil, nil)
	requireSkippedSubscriber(t, sub, cancel, err)
}

func requireSkippedSubscriber(t *testing.T, sub *modelpolicy.Subscriber, cancel context.CancelFunc, err error) {
	t.Helper()
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if sub != nil {
		t.Fatal("expected nil subscriber")
	}
	if cancel != nil {
		t.Fatal("expected nil cancel")
	}
}

func TestUnit_StartModelPolicySubscriber_StartsAndStops(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := modelpolicy.NewCache(mpFakeLoader{}, modelpolicy.Config{CacheTTL: time.Minute, LRUSize: 4}, modelpolicy.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	sub, cancel, err := startModelPolicySubscriber(client, cache, logger.Discard("bootstrap-mp"), nil)
	if err != nil {
		t.Fatal(err)
	}
	if sub == nil || cancel == nil {
		t.Fatal("expected subscriber")
	}
	cancel()
	sub.Stop()
	select {
	case <-sub.Done():
	case <-time.After(3 * time.Second):
		t.Fatal("subscriber did not stop")
	}
}

func mustTestRegistry(t *testing.T) *provider.Registry {
	t.Helper()
	base, err := provider.NewRegistry(
		provider.CapabilityCatalog{
			"gpt-4o": {
				ModelID: "gpt-4o", Provider: provider.CapabilityProviderOpenAI,
				ContextWindow: 128000, MaxOutputTokens: 4096,
				SupportsTools: true, SupportsStreaming: true,
				TokenizerFamily: provider.TokenizerFamilyO200kBase,
			},
		},
		mpStubProvider{name: "openai", models: []string{"gpt-4o"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	return base
}

func assertPassthroughResolver(t *testing.T, resolver interface {
	ForOrg(context.Context, uuid.UUID, string) (provider.Provider, error)
}) {
	t.Helper()
	if _, err := resolver.ForOrg(context.Background(), uuid.New(), "gpt-4o"); err != nil {
		t.Fatalf("passthrough: %v", err)
	}
}

func assertNoopDefaults(t *testing.T, defaults modelpolicy.AgentDefaultLoader) {
	t.Helper()
	got, err := defaults.Load(context.Background(), uuid.New(), uuid.New())
	if err != nil || got.DefaultModel != "" {
		t.Fatalf("noop defaults: %+v err=%v", got, err)
	}
}

func assertModelPolicyEnabledGauge(t *testing.T, reg *ibexmetrics.ProxyRegistry, want float64) {
	t.Helper()
	families, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, f := range families {
		if f.GetName() != "ibex_proxy_model_policy_enabled" {
			continue
		}
		if len(f.GetMetric()) == 0 {
			t.Fatal("enabled gauge has no samples")
		}
		if got := f.GetMetric()[0].GetGauge().GetValue(); got != want {
			t.Fatalf("enabled=%v want %v", got, want)
		}
		return
	}
	t.Fatal("missing ibex_proxy_model_policy_enabled")
}

type mpFakeLoader struct{}

func (mpFakeLoader) LoadOrg(context.Context, uuid.UUID) ([]modelpolicy.Policy, error) {
	return nil, nil
}

type mpStubProvider struct {
	name   string
	models []string
}

func (s mpStubProvider) Name() string              { return s.name }
func (s mpStubProvider) SupportedModels() []string { return s.models }
func (s mpStubProvider) Complete(context.Context, provider.Request) (provider.Response, error) {
	return provider.Response{}, nil
}
