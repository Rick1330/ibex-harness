package tokenizer

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

func TestUnit_BpeLoader_AssetDirOverride(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join("assets", "o200k_base.tiktoken")
	raw, err := os.ReadFile(src)
	require.NoError(t, err)
	require.NoError(t, os.WriteFile(filepath.Join(dir, "o200k_base.tiktoken"), raw, 0o600))

	reg, err := NewLocalRegistry(dir)
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	n, err := tok.Count(context.Background(), "Hello world")
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_ParseBpeLines_Invalid(t *testing.T) {
	_, err := parseBpeLines("not-valid-bpe\n")
	require.Error(t, err)
}

func TestUnit_Registry_Families(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	require.Len(t, reg.Families(), 3)
}

func TestUnit_TiktokenBackend_IsEstimateFalse(t *testing.T) {
	var tok Tokenizer = newTiktokenBackend(provider.TokenizerFamilyO200kBase, "o200k_base", newBundledBpeLoader(""))
	est, ok := tok.(Estimator)
	require.True(t, ok)
	require.False(t, est.IsEstimate())
}

func TestUnit_EstimateClaudeTokens(t *testing.T) {
	require.Equal(t, 4, EstimateClaudeTokens("Hello world"))
}
