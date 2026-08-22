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

	_, err = CountForModel(ModelCountRequest{
		Ctx:     context.Background(),
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     reg,
		Model:   "gpt-4o",
		Text:    "probe",
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_RejectsNilRegistry(t *testing.T) {
	t.Parallel()
	_, err := CountForModel(ModelCountRequest{
		Ctx:     context.Background(),
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     nil,
		Model:   "gpt-4o",
		Text:    "probe",
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_RejectsCanceledContext(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err = CountForModel(ModelCountRequest{
		Ctx: ctx, Catalog: provider.BuiltInCapabilityCatalog(), Reg: reg, Model: "gpt-4o", Text: "probe",
	})
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_CountForModel_RejectsEmptyModelID(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)

	_, err = CountForModel(ModelCountRequest{
		Ctx: context.Background(), Catalog: provider.BuiltInCapabilityCatalog(), Reg: reg, Model: "  ", Text: "probe",
	})
	require.ErrorIs(t, err, ErrModelNotInCatalog)
}

func TestUnit_CountForModel_RejectsMissingCatalogModel(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)
	_, err = CountForModel(ModelCountRequest{
		Ctx: context.Background(), Catalog: provider.BuiltInCapabilityCatalog(), Reg: reg, Model: "missing-model", Text: "probe",
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

	_, err = CountForModel(ModelCountRequest{
		Ctx: context.Background(), Catalog: catalog, Reg: reg, Model: "local", Text: "probe",
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_CountsBuiltinModel(t *testing.T) {
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)

	n, err := CountForModel(ModelCountRequest{
		Ctx:     context.Background(),
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     reg,
		Model:   "gpt-4o",
		Text:    VectorHelloWorld(),
	})
	require.NoError(t, err)
	require.Equal(t, 2, n)
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

	_, err = countForModel(ModelCountRequest{
		Ctx:     context.Background(),
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     reg,
		Model:   "gpt-4o",
		Text:    "probe",
	})
	require.ErrorIs(t, err, wantErr)
}
