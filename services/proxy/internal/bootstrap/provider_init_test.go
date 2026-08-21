package bootstrap

import (
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

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
	}

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	for _, model := range []string{"gpt-4o", "openai/gpt-oss-20b:free"} {
		if _, err := reg.For(model); err != nil {
			t.Fatalf("For(%s): %v", model, err)
		}
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
