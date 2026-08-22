package tokenizer

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

type fixedCountTokenizer struct {
	family string
	n      int
	err    error
}

func (f fixedCountTokenizer) Family() string { return f.family }

func (f fixedCountTokenizer) Count(ctx context.Context, text string) (int, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if f.err != nil {
		return 0, f.err
	}
	return f.n, nil
}

func TestUnit_NewRegistry_RejectsEmptyFamilyKey(t *testing.T) {
	t.Parallel()
	_, err := NewRegistry(map[string]Tokenizer{
		"  ": fixedCountTokenizer{family: provider.TokenizerFamilyO200kBase},
	})
	require.ErrorIs(t, err, ErrUnknownFamily)
}

func TestUnit_NewRegistry_RejectsNilTokenizer(t *testing.T) {
	t.Parallel()
	_, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: nil,
	})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_NewRegistry_RejectsFamilyKeyMismatch(t *testing.T) {
	t.Parallel()
	_, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: newTiktokenBackend(provider.TokenizerFamilyCL100kBase, "cl100k_base", newBundledBpeLoader("")),
	})
	require.ErrorIs(t, err, ErrUnknownFamily)
}

func TestUnit_ValidateCatalogCoverage_RejectsMissingFamily(t *testing.T) {
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

func TestUnit_Registry_NilReceiverReturnsSafeDefaults(t *testing.T) {
	t.Parallel()
	var reg *Registry
	require.Nil(t, reg.Families())
	_, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.ErrorIs(t, err, ErrUnknownFamily)
	require.Error(t, ValidateCatalogCoverage(provider.BuiltInCapabilityCatalog(), nil))
}

func TestUnit_RequiredFamilies_OmitsBlankAndUnknown(t *testing.T) {
	t.Parallel()
	catalog := provider.CatalogFromCapabilities(
		provider.ModelCapability{
			ModelID: "blank", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 1, MaxOutputTokens: 1,
			SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: "  ",
		},
		provider.ModelCapability{
			ModelID: "unknown", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 1, MaxOutputTokens: 1,
			SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyUnknown,
		},
		provider.ModelCapability{
			ModelID: "gpt-4o", Provider: provider.CapabilityProviderOpenAI,
			ContextWindow: 1, MaxOutputTokens: 1,
			SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
			TokenizerFamily: provider.TokenizerFamilyO200kBase,
		},
	)
	require.Equal(t, []string{provider.TokenizerFamilyO200kBase}, RequiredFamilies(catalog))
}

func TestUnit_NewLocalRegistry_CoversBuiltinCatalogFamilies(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	require.NoError(t, ValidateCatalogCoverage(provider.BuiltInCapabilityCatalog(), reg))
}

func TestUnit_Count_RejectsEmptyAndOversizedInput(t *testing.T) {
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

func TestUnit_Count_ConcurrentExactBackend(t *testing.T) {
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

func TestUnit_RunSelfTest_PassesDefaultVectors(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	require.NoError(t, RunSelfTest(reg, DefaultSelfTestVectors()))
}

func TestUnit_RunSelfTest_RejectsNilRegistry(t *testing.T) {
	require.Error(t, RunSelfTest(nil, DefaultSelfTestVectors()))
}

func TestUnit_RunSelfTest_RejectsCountMismatch(t *testing.T) {
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: fixedCountTokenizer{
			family: provider.TokenizerFamilyO200kBase,
			n:      99,
		},
	})
	require.NoError(t, err)
	err = RunSelfTest(reg, []SelfTestVector{{
		Family: provider.TokenizerFamilyO200kBase,
		Text:   vectorHelloWorld,
		Want:   2,
	}})
	require.Error(t, err)
	require.Contains(t, err.Error(), "got 99 want 2")
}

func TestUnit_RunSelfTest_RejectsMissingFamily(t *testing.T) {
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: fixedCountTokenizer{
			family: provider.TokenizerFamilyO200kBase,
			n:      2,
		},
	})
	require.NoError(t, err)
	err = RunSelfTest(reg, []SelfTestVector{{
		Family: provider.TokenizerFamilyCL100kBase,
		Text:   vectorHelloWorld,
		Want:   2,
	}})
	require.Error(t, err)
}

func TestUnit_RunSelfTest_RejectsCountFailure(t *testing.T) {
	wantErr := errors.New("count failed")
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: fixedCountTokenizer{
			family: provider.TokenizerFamilyO200kBase,
			err:    wantErr,
		},
	})
	require.NoError(t, err)
	err = RunSelfTest(reg, []SelfTestVector{{
		Family: provider.TokenizerFamilyO200kBase,
		Text:   vectorHelloWorld,
		Want:   2,
	}})
	require.ErrorIs(t, err, wantErr)
}
