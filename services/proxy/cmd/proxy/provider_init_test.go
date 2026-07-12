package main

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestBuildProviderRegistry_MockModeEmpty(t *testing.T) {
	t.Parallel()
	reg, err := buildProviderRegistry(config.Config{LLMMode: "mock"}, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	if _, err := reg.For("gpt-4o"); err == nil {
		t.Fatal("expected no provider in mock mode")
	}
}

func TestBuildProviderRegistry_LiveModeRegistersOpenAI(t *testing.T) {
	t.Parallel()
	reg, err := buildProviderRegistry(config.Config{
		LLMMode: "live",
		OpenAI: config.OpenAIConfig{
			APIKey: "test-key",
		},
	}, logger.Discard("proxy"), telemetry.NoopTracer("proxy"), metrics.NewProxy("test"))
	if err != nil {
		t.Fatalf("buildProviderRegistry: %v", err)
	}
	if _, err := reg.For("gpt-4o"); err != nil {
		t.Fatalf("For: %v", err)
	}
}
