package tokenizer

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

func TestUnit_NewRegistry_FamilyKeyMismatch(t *testing.T) {
	t.Parallel()
	_, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: newTiktokenBackend(provider.TokenizerFamilyCL100kBase, "cl100k_base", newBundledBpeLoader("")),
	})
	require.ErrorIs(t, err, ErrUnknownFamily)
}

func TestUnit_ValidateCatalogCoverage_MissingFamily(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: newTiktokenBackend(provider.TokenizerFamilyO200kBase, "o200k_base", newBundledBpeLoader("")),
	})
	require.NoError(t, err)
	catalog := provider.CatalogFromCapabilities(provider.ModelCapability{
		ModelID: "m", Provider: provider.CapabilityProviderAnthropic,
		ContextWindow: 1, MaxOutputTokens: 1,
		SupportsTools: true, SupportsVision: true, SupportsStreaming: true,
		TokenizerFamily: provider.TokenizerFamilyClaude,
	})
	err = ValidateCatalogCoverage(catalog, reg)
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_UnknownFamilyOverlay(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	catalog := provider.CatalogFromCapabilities(provider.ModelCapability{
		ModelID: "local", Provider: provider.CapabilityProviderOpenAI,
		ContextWindow: 1, MaxOutputTokens: 1,
		SupportsTools: true, SupportsVision: true, SupportsStreaming: true,
		TokenizerFamily: provider.TokenizerFamilyUnknown,
	})
	_, err = CountForModel(context.Background(), catalog, reg, "local", "hi")
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_MissingModel(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	_, err = CountForModel(context.Background(), provider.BuiltInCapabilityCatalog(), reg, "missing-model", "x")
	require.ErrorIs(t, err, ErrModelNotInCatalog)
}

func TestUnit_NewLocalRegistry_CatalogCoverage(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	require.NoError(t, ValidateCatalogCoverage(provider.BuiltInCapabilityCatalog(), reg))
}

func TestUnit_Count_EmptyAndBounds(t *testing.T) {
	t.Parallel()
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)

	n, err := tok.Count(context.Background(), "")
	require.NoError(t, err)
	require.Equal(t, 0, n)

	long := strings.Repeat("a", MaxCountTextBytes+1)
	_, err = tok.Count(context.Background(), long)
	require.ErrorIs(t, err, ErrTextTooLong)
}

func TestUnit_Count_Concurrent(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyCL100kBase)
	require.NoError(t, err)

	const workers = 16
	errCh := make(chan error, workers)
	for i := 0; i < workers; i++ {
		go func() {
			n, err := tok.Count(context.Background(), vectorHelloWorld)
			if err != nil {
				errCh <- err
				return
			}
			if n != 2 {
				errCh <- fmt.Errorf("unexpected token count: got %d want 2", n)
				return
			}
			errCh <- nil
		}()
	}
	for i := 0; i < workers; i++ {
		require.NoError(t, <-errCh)
	}
}

func TestUnit_RunSelfTest(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	require.NoError(t, RunSelfTest(reg, DefaultSelfTestVectors()))
}
