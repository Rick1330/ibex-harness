package tokenizer

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

type countVector struct {
	text string
	want int
}

func TestUnit_GroundTruthVectors_O200k(t *testing.T) {
	vectors := []countVector{
		{"", 0},
		{"Hello world", 2},
		{"Hello, world!", 4},
		{"🚀", 2},
		{"The quick brown fox jumps over the lazy dog.", 10},
		{"αβγ", 3},
	}
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	runVectors(t, tok, vectors)
}

func TestUnit_GroundTruthVectors_CL100k(t *testing.T) {
	vectors := []countVector{
		{"", 0},
		{"Hello world", 2},
		{"Hello, world!", 4},
		{"🚀", 3},
		{"The quick brown fox jumps over the lazy dog.", 10},
		{"αβγ", 3},
	}
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyCL100kBase)
	require.NoError(t, err)
	runVectors(t, tok, vectors)
}

func TestUnit_GroundTruthVectors_ClaudeEstimate(t *testing.T) {
	vectors := []countVector{
		{"", 0},
		{"Hello world", 4},
		{"Hello, world!", 4},
		{"🚀", 1},
		{"The quick brown fox jumps over the lazy dog.", 13},
		{"αβγ", 1},
	}
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyClaude)
	require.NoError(t, err)
	est, ok := tok.(Estimator)
	require.True(t, ok)
	require.True(t, est.IsEstimate())
	runVectors(t, tok, vectors)
}

func runVectors(t *testing.T, tok Tokenizer, vectors []countVector) {
	t.Helper()
	ctx := context.Background()
	for _, v := range vectors {
		got, err := tok.Count(ctx, v.text)
		require.NoError(t, err)
		require.Equal(t, v.want, got, "text=%q", v.text)
	}
}

func TestUnit_CountForModel_BuiltinGPT4o(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	n, err := CountForModel(context.Background(), provider.BuiltInCapabilityCatalog(), reg, "gpt-4o", "Hello world")
	require.NoError(t, err)
	require.Equal(t, 2, n)
}
