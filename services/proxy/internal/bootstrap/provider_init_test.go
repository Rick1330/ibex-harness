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
			APIKey: "test-key",
		},
	}

	reg, err := buildProviderRegistry(cfg, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))

	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	if _, err := reg.For("gpt-4o"); err != nil {
		t.Fatalf("For: %v", err)
	}
}
