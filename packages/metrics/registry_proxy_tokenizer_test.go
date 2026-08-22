package metrics

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/tokenizer"
	"github.com/stretchr/testify/require"
)

func TestUnit_ObserveTokenizerCount_NilSafe(t *testing.T) {
	var reg *ProxyRegistry
	reg.ObserveTokenizerCount("o200k_base", "success", 0.01)

	reg = &ProxyRegistry{}
	reg.ObserveTokenizerCount("o200k_base", "success", 0.01)
}

func TestUnit_ObserveTokenizerCount_Registered(t *testing.T) {
	reg := NewProxy("tokenizer-metrics-test")
	reg.ObserveTokenizerCount("o200k_base", "success", 0.001)
	reg.ObserveTokenizerCount("claude", "error", 0.002)
}

func TestUnit_TokenizerObserver_SuccessAndCancel(t *testing.T) {
	reg := NewProxy("tokenizer-metrics-test")
	tokReg, err := tokenizer.NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := tokReg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)

	n, err := tokenizer.CountWithObserver(context.Background(), tok, "Hello world", reg)
	require.NoError(t, err)
	require.Equal(t, 2, n)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = tokenizer.CountWithObserver(ctx, tok, "Hello world", reg)
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_TokenizerObserver_CountForModel(t *testing.T) {
	reg := NewProxy("tokenizer-metrics-test")
	tokReg, err := tokenizer.NewLocalRegistry("")
	require.NoError(t, err)
	n, err := tokenizer.CountForModelWithObserver(
		context.Background(),
		provider.BuiltInCapabilityCatalog(),
		tokReg,
		"gpt-4o",
		"Hello world",
		reg,
	)
	require.NoError(t, err)
	require.Equal(t, 2, n)
}
