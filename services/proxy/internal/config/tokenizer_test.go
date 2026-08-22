package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestUnit_ValidateTokenizer_ServiceModeRejected(t *testing.T) {
	cfg := Config{Tokenizer: TokenizerConfig{Mode: "service"}}
	cfg.ApplyDefaults()
	require.Error(t, cfg.validateTokenizer())
	require.ErrorContains(t, cfg.validateTokenizer(), "not implemented")
}

func TestUnit_ValidateTokenizer_LocalDefault(t *testing.T) {
	cfg := Config{}
	cfg.ApplyDefaults()
	require.NoError(t, cfg.validateTokenizer())
	require.Equal(t, "local", cfg.Tokenizer.Mode)
}

func TestUnit_ApplyTokenizerDefaults_NormalizesMode(t *testing.T) {
	for _, tc := range []struct {
		in   string
		want string
	}{
		{in: " LOCAL ", want: "local"},
		{in: "LOCAL", want: "local"},
	} {
		cfg := Config{Tokenizer: TokenizerConfig{Mode: tc.in}}
		cfg.ApplyDefaults()
		require.Equal(t, tc.want, cfg.Tokenizer.Mode)
	}
}
