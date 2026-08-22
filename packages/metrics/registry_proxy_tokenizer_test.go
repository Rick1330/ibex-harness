package metrics

import (
	"context"
	"strings"
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

	body := scrapeMetrics(t, reg.Gatherer())
	require.True(t, strings.Contains(body, "ibex_tokenizer_count_total"))
	require.True(t, strings.Contains(body, "ibex_tokenizer_count_duration_seconds"))

	families := gatherFamilies(t, reg.Gatherer())
	counter := families["ibex_tokenizer_count_total"]
	require.NotNil(t, counter)
	require.Equal(t, float64(1), counterByLabels(counter, map[string]string{
		"family": "o200k_base", "result": "success",
	}))
	require.Equal(t, float64(1), counterByLabels(counter, map[string]string{
		"family": "claude", "result": "error",
	}))

	hist := families["ibex_tokenizer_count_duration_seconds"]
	require.NotNil(t, hist)
	require.NotEmpty(t, hist.GetMetric())
}

func TestUnit_TokenizerObserver_SuccessAndCancel(t *testing.T) {
	reg := NewProxy("tokenizer-metrics-test")
	tokReg, err := tokenizer.NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := tokReg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)

	n, err := tokenizer.CountWithObserver(context.Background(), tok, tokenizer.VectorHelloWorld(), reg)
	require.NoError(t, err)
	require.Equal(t, 2, n)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = tokenizer.CountWithObserver(ctx, tok, tokenizer.VectorHelloWorld(), reg)
	require.ErrorIs(t, err, context.Canceled)

	families := gatherFamilies(t, reg.Gatherer())
	counter := families["ibex_tokenizer_count_total"]
	require.Equal(t, float64(1), counterByLabels(counter, map[string]string{
		"family": provider.TokenizerFamilyO200kBase, "result": "success",
	}))
	require.Equal(t, float64(1), counterByLabels(counter, map[string]string{
		"family": provider.TokenizerFamilyO200kBase, "result": "error",
	}))
}

func TestUnit_TokenizerObserver_CountForModel(t *testing.T) {
	reg := NewProxy("tokenizer-metrics-test")
	tokReg, err := tokenizer.NewLocalRegistry("")
	require.NoError(t, err)
	n, err := tokenizer.CountForModelWithObserver(tokenizer.ModelCountObserveRequest{
		ModelCountRequest: tokenizer.ModelCountRequest{
			Ctx:     context.Background(),
			Catalog: provider.BuiltInCapabilityCatalog(),
			Reg:     tokReg,
			Model:   "gpt-4o",
			Text:    tokenizer.VectorHelloWorld(),
		},
		Obs: reg,
	})
	require.NoError(t, err)
	require.Equal(t, 2, n)

	families := gatherFamilies(t, reg.Gatherer())
	hist := families["ibex_tokenizer_count_duration_seconds"]
	require.NotNil(t, hist)
	metrics := hist.GetMetric()
	require.NotEmpty(t, metrics)
	for _, m := range metrics {
		for _, lp := range m.GetLabel() {
			if lp.GetName() == "family" {
				require.Equal(t, provider.TokenizerFamilyO200kBase, lp.GetValue())
			}
		}
	}
}
