package bootstrap

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_BuildModelPolicyRuntime_NilPostgresPassthrough(t *testing.T) {
	t.Parallel()
	base, err := provider.NewRegistry(
		provider.CapabilityCatalog{
			"gpt-4o": {
				ModelID: "gpt-4o", Provider: provider.CapabilityProviderOpenAI,
				ContextWindow: 128000, MaxOutputTokens: 4096,
				SupportsTools: true, SupportsStreaming: true,
				TokenizerFamily: provider.TokenizerFamilyO200kBase,
			},
		},
		stubProvider{name: "openai", models: []string{"gpt-4o"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	cache, resolver, defaults, err := buildModelPolicyRuntime(nil, base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if cache != nil {
		t.Fatal("expected nil cache without postgres")
	}
	_, err = resolver.ForOrg(context.Background(), uuid.New(), "gpt-4o")
	if err != nil {
		t.Fatalf("passthrough: %v", err)
	}
	got, err := defaults.Load(context.Background(), uuid.New(), uuid.New())
	if err != nil || got.DefaultModel != "" {
		t.Fatalf("noop defaults: %+v err=%v", got, err)
	}
}

func TestUnit_StartModelPolicySubscriber_SkippedWithoutDeps(t *testing.T) {
	t.Parallel()
	sub, cancel, err := startModelPolicySubscriber(nil, nil, nil, nil)
	if err != nil || sub != nil || cancel != nil {
		t.Fatalf("sub=%v cancel=%v err=%v", sub, cancel, err)
	}
}

func TestUnit_StartModelPolicySubscriber_StartsAndStops(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	loader := &mpFakeLoader{}
	cache, err := modelpolicy.NewCache(loader, modelpolicy.Config{CacheTTL: time.Minute, LRUSize: 4}, modelpolicy.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	log := logger.Discard("bootstrap-mp")
	sub, cancel, err := startModelPolicySubscriber(client, cache, log, nil)
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

type mpFakeLoader struct{}

func (mpFakeLoader) LoadOrg(context.Context, uuid.UUID) ([]modelpolicy.Policy, error) {
	return nil, nil
}

type stubProvider struct {
	name   string
	models []string
}

func (s stubProvider) Name() string              { return s.name }
func (s stubProvider) SupportedModels() []string { return s.models }
func (s stubProvider) Complete(context.Context, provider.Request) (provider.Response, error) {
	return provider.Response{}, nil
}
