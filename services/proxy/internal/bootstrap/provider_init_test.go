package bootstrap

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/provider/anthropic"
	"github.com/Rick1330/ibex-harness/packages/provider/openai"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestBuildProviderRegistry_CatalogCoversProviderSupportedModels(t *testing.T) {
	t.Parallel()
	catalog := provider.BuiltInCapabilityCatalog()
	oai := openai.New(openai.Config{APIKey: "k"}, logger.Discard("t"), telemetry.NoopTracer("t"), metrics.NewProxy("t"))
	anth := anthropic.New(anthropic.Config{APIKey: "k"}, logger.Discard("t"), telemetry.NoopTracer("t"), metrics.NewProxy("t"))
	for _, model := range append(oai.SupportedModels(), anth.SupportedModels()...) {
		if _, ok := catalog.Lookup(model); !ok {
			t.Fatalf("SupportedModels id %q missing from BuiltInCapabilityCatalog", model)
		}
	}
}

func TestBuildProviderRegistry_MockModeIgnoresExtraModelsAndOverlays(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		Environment: "development",
		LLMMode:     "mock",
		OpenAI: config.OpenAIConfig{
			ExtraModels: []string{"openai/gpt-oss-20b:free"},
		},
		ModelCapabilityOverlays: []provider.ModelCapability{{
			ModelID: "openai/gpt-oss-20b:free", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 8192, MaxOutputTokens: 1024,
			SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyUnknown,
		}},
	}
	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	if _, err := reg.For("openai/gpt-oss-20b:free"); err == nil {
		t.Fatal("ExtraModels must not register under mock")
	}
	if _, ok := reg.Capability("openai/gpt-oss-20b:free"); ok {
		t.Fatal("overlays must not register under mock")
	}
}

func TestBuildProviderRegistry_MockModeRegistersMock(t *testing.T) {
	t.Parallel()

	cfg := config.Config{
		Environment: "development",
		LLMMode:     "mock",
	}

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))

	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	p, err := reg.For("gpt-4o")
	if err != nil {
		t.Fatalf("For: %v", err)
	}
	if p.Name() != "mock" {
		t.Fatalf("provider=%q", p.Name())
	}
}

func TestBuildProviderRegistry_MockModeRejectedInProduction(t *testing.T) {
	t.Parallel()

	cfg := config.Config{
		Environment: "production",
		LLMMode:     "mock",
	}

	_, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))

	if err == nil {
		t.Fatal("expected error for mock mode in production")
	}
	if !strings.Contains(err.Error(), "production") {
		t.Fatalf("err=%v", err)
	}
}

func TestBuildProviderRegistry_LiveModeRegistersOpenAI(t *testing.T) {
	t.Parallel()

	cfg := config.Config{
		LLMMode: "live",
		OpenAI: config.OpenAIConfig{
			APIKey:      "test-key",
			ExtraModels: []string{"openai/gpt-oss-20b:free"},
		},
		ModelCapabilityOverlays: []provider.ModelCapability{{
			ModelID:           "openai/gpt-oss-20b:free",
			Provider:          provider.CapabilityProviderOpenAI,
			ContextWindow:     8192,
			MaxOutputTokens:   2048,
			SupportsTools:     false,
			SupportsVision:    false,
			SupportsStreaming: true,
			TokenizerFamily:   provider.TokenizerFamilyUnknown,
		}},
	}

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	for _, model := range []string{"gpt-4o", "openai/gpt-oss-20b:free"} {
		if _, err := reg.For(model); err != nil {
			t.Fatalf("For(%s): %v", model, err)
		}
		if _, ok := reg.Capability(model); !ok {
			t.Fatalf("Capability(%s): missing", model)
		}
	}
}

func TestBuildProviderRegistry_LiveModeExtraModelsRequireOverlay(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		LLMMode: "live",
		OpenAI: config.OpenAIConfig{
			APIKey: "test-key", ExtraModels: []string{"openai/gpt-oss-20b:free"},
		},
	}
	_, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err == nil || !strings.Contains(err.Error(), "openai/gpt-oss-20b:free") {
		t.Fatalf("err=%v", err)
	}
}

func TestBuildProviderRegistry_BuiltinListedInExtraModelsNeedsNoOverlay(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		LLMMode: "live",
		OpenAI: config.OpenAIConfig{
			APIKey: "test-key", ExtraModels: []string{"gpt-4o"},
		},
	}
	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	if _, ok := reg.Capability("gpt-4o"); !ok {
		t.Fatal("Capability(gpt-4o): missing")
	}
}

func TestBuildProviderRegistry_InvalidOverlayProviderRejected(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		LLMMode: "live",
		OpenAI: config.OpenAIConfig{
			APIKey: "test-key", ExtraModels: []string{"openai/gpt-oss-20b:free"},
		},
		ModelCapabilityOverlays: []provider.ModelCapability{{
			ModelID: "openai/gpt-oss-20b:free", Provider: "", ContextWindow: 8192, MaxOutputTokens: 1024,
			SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyUnknown,
		}},
	}
	_, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err == nil || !strings.Contains(err.Error(), "provider must be") {
		t.Fatalf("err=%v", err)
	}
}

func TestBuildProviderRegistry_RejectsBuiltinAndOrphanOverlays(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		cfg     config.Config
		wantErr string
	}{
		{
			name: "builtin overlay",
			cfg: config.Config{
				LLMMode: "live",
				OpenAI:  config.OpenAIConfig{APIKey: "k"},
				ModelCapabilityOverlays: []provider.ModelCapability{{
					ModelID: "gpt-4o", Provider: provider.CapabilityProviderOpenAI, ContextWindow: 1, MaxOutputTokens: 1,
					SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
					TokenizerFamily: provider.TokenizerFamilyUnknown,
				}},
			},
			wantErr: "cannot override built-in",
		},
		{
			name: "orphan overlay",
			cfg: config.Config{
				LLMMode: "live",
				OpenAI:  config.OpenAIConfig{APIKey: "k"},
				ModelCapabilityOverlays: []provider.ModelCapability{{
					ModelID: "orphan-model", Provider: provider.CapabilityProviderOpenAI, ContextWindow: 8192, MaxOutputTokens: 1024,
					SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
					TokenizerFamily: provider.TokenizerFamilyUnknown,
				}},
			},
			wantErr: "not listed",
		},
	}
	assertRegistryErrContains(t, cases)
}

func TestBuildProviderRegistry_RejectsExtrasWithoutOverlayOrKey(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name    string
		cfg     config.Config
		wantErr string
	}{
		{
			name: "anthropic extra without overlay",
			cfg: config.Config{
				LLMMode: "live",
				Anthropic: config.AnthropicConfig{
					APIKey: "anth-key", ExtraModels: []string{"claude-custom"},
				},
			},
			wantErr: "claude-custom",
		},
		{
			name: "extras without api key",
			cfg: config.Config{
				LLMMode: "live",
				OpenAI:  config.OpenAIConfig{APIKey: "k"},
				Anthropic: config.AnthropicConfig{
					ExtraModels: []string{"claude-custom"},
				},
			},
			wantErr: "ANTHROPIC_API_KEY",
		},
		{
			name: "overlay provider mismatch",
			cfg: config.Config{
				LLMMode: "live",
				OpenAI: config.OpenAIConfig{
					APIKey: "k", ExtraModels: []string{"openai/gpt-oss-20b:free"},
				},
				ModelCapabilityOverlays: []provider.ModelCapability{{
					ModelID: "openai/gpt-oss-20b:free", Provider: provider.CapabilityProviderAnthropic,
					ContextWindow: 8192, MaxOutputTokens: 1024,
					SupportsTools: false, SupportsVision: false, SupportsStreaming: true,
					TokenizerFamily: provider.TokenizerFamilyUnknown,
				}},
			},
			wantErr: "provider must be",
		},
	}
	assertRegistryErrContains(t, cases)
}

func TestBuildProviderRegistry_OpenAIOnlyRejectsAnthropicExtrasWithoutKey(t *testing.T) {
	t.Parallel()
	cfg := config.Config{
		LLMMode: "live",
		OpenAI:  config.OpenAIConfig{APIKey: "k"},
		Anthropic: config.AnthropicConfig{
			ExtraModels: []string{"claude-custom"},
		},
	}
	_, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err == nil || !strings.Contains(err.Error(), "ANTHROPIC_API_KEY") {
		t.Fatalf("err=%v", err)
	}
}

func assertRegistryErrContains(t *testing.T, cases []struct {
	name    string
	cfg     config.Config
	wantErr string
}) {
	t.Helper()
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := buildProviderRegistry(tc.cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
			if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("err=%v want substring %q", err, tc.wantErr)
			}
		})
	}
}

func TestBuildProviderRegistry_LiveModeRegistersAnthropicOnly(t *testing.T) {
	t.Parallel()

	cfg := config.Config{
		LLMMode: "live",
		Anthropic: config.AnthropicConfig{
			APIKey: "anth-key",
		},
	}

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	p, err := reg.For("claude-sonnet-4-5")
	if err != nil {
		t.Fatalf("For: %v", err)
	}
	if p.Name() != "anthropic" {
		t.Fatalf("provider=%q", p.Name())
	}
	if _, err := reg.For("gpt-4o"); err == nil {
		t.Fatal("expected gpt-4o unregistered without OpenAI key")
	}
}

func TestBuildProviderRegistry_LiveModeRegistersBoth(t *testing.T) {
	t.Parallel()

	cfg := config.Config{
		LLMMode: "live",
		OpenAI: config.OpenAIConfig{
			APIKey: "openai-key",
		},
		Anthropic: config.AnthropicConfig{
			APIKey: "anth-key",
		},
	}

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	if _, err := reg.For("gpt-4o"); err != nil {
		t.Fatalf("openai: %v", err)
	}
	if _, err := reg.For("claude-sonnet-4-5"); err != nil {
		t.Fatalf("anthropic: %v", err)
	}
}

func TestBuildProviderRegistry_LiveModeRequiresCredential(t *testing.T) {
	t.Parallel()

	_, err := buildProviderRegistry(config.Config{LLMMode: "live"}, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "OPENAI_API_KEY") {
		t.Fatalf("err=%v", err)
	}
}
