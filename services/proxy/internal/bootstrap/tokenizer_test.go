package bootstrap

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/tokenizer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/stretchr/testify/require"
)

func mockTokenizerConfig() config.Config {
	cfg := config.Config{LLMMode: "mock"}
	cfg.ApplyDefaults()
	return cfg
}

func TestUnit_BuildTokenizerRegistry_MockMode(t *testing.T) {
	reg, err := buildTokenizerRegistry(mockTokenizerConfig())
	require.NoError(t, err)
	require.NotNil(t, reg)
}

func TestUnit_BuildTokenizerRegistry_RejectsServiceMode(t *testing.T) {
	cfg := config.Config{Tokenizer: config.TokenizerConfig{Mode: "service"}}
	cfg.ApplyDefaults()
	_, err := buildTokenizerRegistry(cfg)
	require.Error(t, err)
}

func TestUnit_BuildTokenizerRegistry_RejectsDualMode(t *testing.T) {
	cfg := config.Config{Tokenizer: config.TokenizerConfig{Mode: "dual"}, LLMMode: "mock"}
	cfg.ApplyDefaults()
	_, err := buildTokenizerRegistry(cfg)
	require.Error(t, err)
	require.Contains(t, err.Error(), "IBEX_TOKENIZER_MODE")
}

func TestUnit_BuildLocalTokenizerRegistry_RejectsInvalidConfig(t *testing.T) {
	cases := []struct {
		name string
		cfg  config.Config
	}{
		{
			name: "missing asset dir",
			cfg: config.Config{
				LLMMode: "mock",
				Tokenizer: config.TokenizerConfig{
					AssetDir: filepath.Join(t.TempDir(), "missing-subdir"),
				},
			},
		},
		{
			name: "live catalog without api key",
			cfg: config.Config{
				LLMMode: "openai",
				OpenAI: config.OpenAIConfig{
					ExtraModels: []string{"custom-model"},
				},
			},
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := tc.cfg
			cfg.ApplyDefaults()
			_, err := buildLocalTokenizerRegistry(cfg)
			require.Error(t, err)
			require.Contains(t, err.Error(), "tokenizer registry")
		})
	}
}

func TestUnit_NewTokenizerReadyChecker_CanceledContext(t *testing.T) {
	reg, err := buildTokenizerRegistry(mockTokenizerConfig())
	require.NoError(t, err)
	checker := newTokenizerReadyChecker(reg)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	require.ErrorIs(t, checker(ctx), context.Canceled)
}

func TestUnit_BuildTokenizerRegistry_CatalogCoverage(t *testing.T) {
	reg, err := buildTokenizerRegistry(mockTokenizerConfig())
	require.NoError(t, err)
	n, err := countForBuiltinModel(reg, "gpt-4o", tokenizer.VectorHelloWorld())
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_BuildProxyHealth_IncludesTokenizer(t *testing.T) {
	reg, err := buildTokenizerRegistry(mockTokenizerConfig())
	require.NoError(t, err)
	h := buildProxyHealth(mockTokenizerConfig(), nil, nil, reg)
	require.Contains(t, h.AdvisoryCheckers, "tokenizer")
}
