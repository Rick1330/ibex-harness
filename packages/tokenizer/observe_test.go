package tokenizer

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

type stubObserver struct {
	calls []obsCall
}

type obsCall struct {
	family string
	result string
}

func (s *stubObserver) ObserveTokenizerCount(family, result string, _ float64) {
	s.calls = append(s.calls, obsCall{family: family, result: result})
}

func TestUnit_CountWithObserver_RecordsSuccessAndError(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	obs := &stubObserver{}

	n, err := CountWithObserver(context.Background(), tok, vectorHelloWorld, obs)
	require.NoError(t, err)
	require.Equal(t, 2, n)
	require.Len(t, obs.calls, 1)
	require.Equal(t, provider.TokenizerFamilyO200kBase, obs.calls[0].family)
	require.Equal(t, "success", obs.calls[0].result)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = CountWithObserver(ctx, tok, vectorHelloWorld, obs)
	require.ErrorIs(t, err, context.Canceled)
	require.Len(t, obs.calls, 2)
	require.Equal(t, "error", obs.calls[1].result)
}

func TestUnit_CountWithObserver_NilObserver(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	n, err := CountWithObserver(context.Background(), tok, vectorHelloWorld, nil)
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_CountForModelWithObserver_SkipsMetricsWhenObserverNil(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	n, err := CountForModelWithObserver(ModelCountObserveRequest{
		ModelCountRequest: ModelCountRequest{
			Ctx: context.Background(), Catalog: provider.BuiltInCapabilityCatalog(),
			Reg: reg, Model: "gpt-4o", Text: vectorHelloWorld,
		},
	})
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_ObserverFamilyLabel_ReturnsUnknownForMissingModel(t *testing.T) {
	require.Equal(t, "unknown", observerFamilyLabel(provider.BuiltInCapabilityCatalog(), "missing-model"))
}

func TestUnit_ObserverFamilyLabel_ReturnsUnknownForBlankFamily(t *testing.T) {
	catalog := provider.CatalogFromCapabilities(provider.ModelCapability{
		ModelID: "overlay", Provider: provider.CapabilityProviderOpenAI,
		ContextWindow: 1, MaxOutputTokens: 1,
		SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
		TokenizerFamily: "",
	})
	require.Equal(t, "unknown", observerFamilyLabel(catalog, "overlay"))
}

func TestUnit_CountForModelWithObserver_ErrorPaths(t *testing.T) {
	obs := &stubObserver{}
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)

	_, err = CountForModelWithObserver(ModelCountObserveRequest{
		ModelCountRequest: ModelCountRequest{
			Ctx: context.Background(), Catalog: provider.BuiltInCapabilityCatalog(),
			Reg: nil, Model: "gpt-4o", Text: "x",
		},
		Obs: obs,
	})
	require.Error(t, err)
	require.Len(t, obs.calls, 1)
	require.Equal(t, provider.TokenizerFamilyO200kBase, obs.calls[0].family)
	require.Equal(t, "error", obs.calls[0].result)

	_, err = CountForModelWithObserver(ModelCountObserveRequest{
		ModelCountRequest: ModelCountRequest{
			Ctx: context.Background(), Catalog: provider.BuiltInCapabilityCatalog(),
			Reg: reg, Model: "missing", Text: "x",
		},
		Obs: obs,
	})
	require.Error(t, err)
	require.GreaterOrEqual(t, len(obs.calls), 2)
	require.Equal(t, "unknown", obs.calls[len(obs.calls)-1].family)
}

func TestUnit_CountForModelWithObserver_PreservesFamilyOnCountFailure(t *testing.T) {
	obs := &stubObserver{}
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = CountForModelWithObserver(ModelCountObserveRequest{
		ModelCountRequest: ModelCountRequest{
			Ctx: ctx, Catalog: provider.BuiltInCapabilityCatalog(),
			Reg: reg, Model: "gpt-4o", Text: vectorHelloWorld,
		},
		Obs: obs,
	})
	require.ErrorIs(t, err, context.Canceled)
	require.Len(t, obs.calls, 1)
	require.Equal(t, provider.TokenizerFamilyO200kBase, obs.calls[0].family)
	require.Equal(t, "error", obs.calls[0].result)
}
