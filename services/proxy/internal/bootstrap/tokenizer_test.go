package bootstrap

import (
	"testing"

	"github.com/Rick1330/ibex-harness/packages/tokenizer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/stretchr/testify/require"
)

func TestUnit_BuildTokenizerRegistry_MockMode(t *testing.T) {
	cfg := config.Config{LLMMode: "mock"}
	cfg.ApplyDefaults()
	reg, err := buildTokenizerRegistry(cfg)
	require.NoError(t, err)
	require.NotNil(t, reg)
}

func TestUnit_BuildTokenizerRegistry_UnsupportedMode(t *testing.T) {
	cfg := config.Config{Tokenizer: config.TokenizerConfig{Mode: "service"}}
	cfg.ApplyDefaults()
	_, err := buildTokenizerRegistry(cfg)
	require.Error(t, err)
}

func TestUnit_BuildTokenizerRegistry_CatalogCoverage(t *testing.T) {
	cfg := config.Config{LLMMode: "mock"}
	cfg.ApplyDefaults()
	reg, err := buildTokenizerRegistry(cfg)
	require.NoError(t, err)
	n, err := countForBuiltinModel(reg, "gpt-4o", tokenizer.VectorHelloWorld())
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_BuildProxyHealth_IncludesTokenizer(t *testing.T) {
	cfg := config.Config{LLMMode: "mock"}
	cfg.ApplyDefaults()
	reg, err := buildTokenizerRegistry(cfg)
	require.NoError(t, err)
	h := buildProxyHealth(cfg, nil, nil, reg)
	require.Contains(t, h.AdvisoryCheckers, "tokenizer")
}
