package bootstrap

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/tokenizer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/stretchr/testify/require"
)

func TestIntegration_BuildTokenizerRegistry_FromEnvDefaults(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_LLM_MODE", "mock")
	t.Setenv("IBEX_TOKENIZER_MODE", "local")
	cfg, err := config.Load()
	require.NoError(t, err)
	reg, err := buildTokenizerRegistry(cfg)
	require.NoError(t, err)
	require.NotNil(t, reg)
	_, err = countForBuiltinModel(reg, "claude-sonnet-4-5", "Hello world")
	require.NoError(t, err)
}

func TestIntegration_TokenizerReadyChecker_Advisory(t *testing.T) {
	cfg := config.Config{LLMMode: "mock"}
	cfg.ApplyDefaults()
	reg, err := buildTokenizerRegistry(cfg)
	require.NoError(t, err)
	checker := newTokenizerReadyChecker(reg)
	require.NoError(t, checker(context.Background()))

	h := buildProxyHealth(cfg, nil, nil, reg)
	require.Contains(t, h.AdvisoryCheckers, "tokenizer")
}

func TestIntegration_TokenizerRegistry_FailsOnInvalidModeConfig(t *testing.T) {
	t.Setenv("IBEX_ENV", "development")
	t.Setenv("IBEX_LLM_MODE", "mock")
	t.Setenv("IBEX_TOKENIZER_MODE", "service")
	_, err := config.Load()
	require.Error(t, err)
	require.Contains(t, err.Error(), "IBEX_TOKENIZER_MODE")
}

func TestIntegration_UnknownFamilyOverlay_CountFailsAtRuntime(t *testing.T) {
	cfg := config.Config{LLMMode: "mock"}
	cfg.ApplyDefaults()
	reg, err := buildTokenizerRegistry(cfg)
	require.NoError(t, err)
	catalog := provider.CatalogFromCapabilities(provider.ModelCapability{
		ModelID: "custom-model", Provider: provider.CapabilityProviderOpenAI,
		ContextWindow: 8192, MaxOutputTokens: 1024,
		SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
		TokenizerFamily: provider.TokenizerFamilyUnknown,
	})
	_, err = tokenizer.CountForModel(context.Background(), catalog, reg, "custom-model", "hi")
	require.ErrorIs(t, err, tokenizer.ErrMissingTokenizer)
}
