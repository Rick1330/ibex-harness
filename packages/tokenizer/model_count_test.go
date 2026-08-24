package tokenizer

import (
	"context"
	"errors"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

func TestUnit_CountForModel_RejectsMissingRegistryFamily(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyClaude: newClaudeEstimate(),
	})
	require.NoError(t, err)

	_, err = CountForModel(context.Background(), ModelCountRequest{
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     reg,
		Model:   "gpt-4o",
		Text:    "probe",
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_RejectsNilRegistry(t *testing.T) {
	t.Parallel()
	_, err := CountForModel(context.Background(), ModelCountRequest{
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     nil,
		Model:   "gpt-4o",
		Text:    "probe",
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_BuiltinCatalog(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	cases := []struct {
		name    string
		ctx     context.Context
		model   string
		text    string
		wantErr error
		wantN   int
	}{
		{name: "canceled context", ctx: ctx, model: "gpt-4o", text: "probe", wantErr: context.Canceled},
		{name: "empty model id", ctx: context.Background(), model: "  ", text: "probe", wantErr: ErrModelNotInCatalog},
		{name: "counts builtin", ctx: context.Background(), model: "gpt-4o", text: VectorHelloWorld(), wantN: 2},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			n, err := CountForModel(tc.ctx, ModelCountRequest{
				Catalog: provider.BuiltInCapabilityCatalog(),
				Reg:     reg,
				Model:   tc.model,
				Text:    tc.text,
			})
			if tc.wantErr != nil {
				require.ErrorIs(t, err, tc.wantErr)
				return
			}
			require.NoError(t, err)
			require.Equal(t, tc.wantN, n)
		})
	}
}

func TestUnit_CountForModel_RejectsMissingCatalogModel(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)
	_, err = CountForModel(context.Background(), ModelCountRequest{
		Catalog: provider.BuiltInCapabilityCatalog(), Reg: reg, Model: "missing-model", Text: "probe",
	})
	require.ErrorIs(t, err, ErrModelNotInCatalog)
}

func TestUnit_CountForModel_RejectsUnknownCatalogFamily(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)
	catalog := provider.CatalogFromCapabilities(provider.ModelCapability{
		ModelID: "local", Provider: provider.CapabilityProviderOpenAI,
		ContextWindow: 1, MaxOutputTokens: 1,
		SupportsTools: true, SupportsVision: true, SupportsStreaming: true,
		TokenizerFamily: provider.TokenizerFamilyUnknown,
	})

	_, err = CountForModel(context.Background(), ModelCountRequest{
		Catalog: catalog, Reg: reg, Model: "local", Text: "probe",
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_countForModel_PropagatesTokenizerError(t *testing.T) {
	t.Parallel()
	wantErr := errors.New("count failed")
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: fixedCountTokenizer{
			family: provider.TokenizerFamilyO200kBase,
			err:    wantErr,
		},
	})
	require.NoError(t, err)

	_, err = countForModel(context.Background(), ModelCountRequest{
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     reg,
		Model:   "gpt-4o",
		Text:    "probe",
	})
	require.ErrorIs(t, err, wantErr)
}
