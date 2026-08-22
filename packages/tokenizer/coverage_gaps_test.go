package tokenizer

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/Rick1330/ibex-harness/packages/provider"
	tiktoken "github.com/pkoukk/tiktoken-go"
	"github.com/stretchr/testify/require"
)

type stubTokenizer struct {
	family string
	n      int
	err    error
}

func (s stubTokenizer) Family() string { return s.family }

func (s stubTokenizer) Count(ctx context.Context, text string) (int, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if s.err != nil {
		return 0, s.err
	}
	return s.n, nil
}

func TestUnit_SanitizeAssetBasename_RejectsInvalid(t *testing.T) {
	_, err := sanitizeAssetBasename("")
	require.ErrorIs(t, err, ErrAssetPathEscape)
	_, err = sanitizeAssetBasename("nested/name.tiktoken")
	require.ErrorIs(t, err, ErrAssetPathEscape)
}

func TestUnit_JailedAssetPath_Success(t *testing.T) {
	dir := t.TempDir()
	path, err := jailedAssetPath(dir, "o200k_base.tiktoken")
	require.NoError(t, err)
	require.Equal(t, filepath.Join(dir, "o200k_base.tiktoken"), path)
}

func TestUnit_LoadBpeFromAssetDir_CorruptOverride(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, "o200k_base.tiktoken"), []byte("bad"), 0o600))
	_, found, err := loadBpeFromAssetDir(dir, "o200k_base.tiktoken")
	require.True(t, found)
	require.Error(t, err)
}

func TestUnit_ParseBpeLine_InvalidCases(t *testing.T) {
	_, _, err := parseBpeLine("only-one-field")
	require.ErrorIs(t, err, errInvalidBpeLine)
	_, _, err = parseBpeLine("!!! 0")
	require.Error(t, err)
	_, _, err = parseBpeLine("YQ== not-a-rank")
	require.Error(t, err)
}

func TestUnit_ReadBoundedFSFile_OpenError(t *testing.T) {
	_, err := readBoundedFSFile(fstest.MapFS{}, "missing.tiktoken", 1024)
	require.Error(t, err)
	require.ErrorIs(t, err, fs.ErrNotExist)
}

func TestUnit_NewRegistry_ValidationErrors(t *testing.T) {
	t.Parallel()
	_, err := NewRegistry(map[string]Tokenizer{"  ": stubTokenizer{family: "x"}})
	require.ErrorIs(t, err, ErrUnknownFamily)

	_, err = NewRegistry(map[string]Tokenizer{provider.TokenizerFamilyO200kBase: nil})
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_Registry_NilReceiverHelpers(t *testing.T) {
	t.Parallel()
	var reg *Registry
	require.Nil(t, reg.Families())
	_, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.ErrorIs(t, err, ErrUnknownFamily)
	require.Error(t, ValidateCatalogCoverage(provider.BuiltInCapabilityCatalog(), nil))
}

func TestUnit_RequiredFamilies_SkipsBlankAndUnknown(t *testing.T) {
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
	families := RequiredFamilies(catalog)
	require.Contains(t, families, provider.TokenizerFamilyO200kBase)
	require.NotContains(t, families, provider.TokenizerFamilyUnknown)
}

func TestUnit_CountForModel_RegistryMissingFamily(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyClaude: newClaudeEstimate(),
	})
	require.NoError(t, err)
	_, err = CountForModel(
		context.Background(),
		provider.BuiltInCapabilityCatalog(),
		reg,
		"gpt-4o",
		"x",
	)
	require.ErrorIs(t, err, ErrUnknownFamily)
}

func TestUnit_CountWithObserver_RecordsOutcomes(t *testing.T) {
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

func TestUnit_ObserverFamilyLabel_UnknownAndEmptyFamily(t *testing.T) {
	require.Equal(t, "unknown", observerFamilyLabel(provider.BuiltInCapabilityCatalog(), "missing-model"))

	catalog := provider.CatalogFromCapabilities(provider.ModelCapability{
		ModelID: "overlay", Provider: provider.CapabilityProviderOpenAI,
		ContextWindow: 1, MaxOutputTokens: 1,
		SupportsTools: true, SupportsVision: false, SupportsStreaming: true,
		TokenizerFamily: "",
	})
	require.Equal(t, "unknown", observerFamilyLabel(catalog, "overlay"))
}

func TestUnit_CountForModelWithObserver_NilObserver(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	n, err := CountForModelWithObserver(
		context.Background(),
		provider.BuiltInCapabilityCatalog(),
		reg,
		"gpt-4o",
		vectorHelloWorld,
		nil,
	)
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_RunSelfTest_ErrorPaths(t *testing.T) {
	require.Error(t, RunSelfTest(nil, DefaultSelfTestVectors()))

	reg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: stubTokenizer{
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

	err = RunSelfTest(reg, []SelfTestVector{{
		Family: provider.TokenizerFamilyCL100kBase,
		Text:   vectorHelloWorld,
		Want:   2,
	}})
	require.Error(t, err)

	countErrReg, err := NewRegistry(map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase: stubTokenizer{
			family: provider.TokenizerFamilyO200kBase,
			err:    errors.New("count failed"),
		},
	})
	require.NoError(t, err)
	err = RunSelfTest(countErrReg, []SelfTestVector{{
		Family: provider.TokenizerFamilyO200kBase,
		Text:   vectorHelloWorld,
		Want:   2,
	}})
	require.Error(t, err)
	require.Contains(t, err.Error(), "count failed")
}

func TestUnit_Claude_CountValidationAndCancel(t *testing.T) {
	tok := newClaudeEstimate()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := tok.Count(ctx, vectorHelloWorld)
	require.ErrorIs(t, err, context.Canceled)

	long := strings.Repeat("a", MaxCountTextBytes+1)
	_, err = tok.Count(context.Background(), long)
	require.ErrorIs(t, err, ErrTextTooLong)
}

type failBpeLoader struct{}

func (failBpeLoader) LoadTiktokenBpe(string) (map[string]int, error) {
	return nil, errors.New("bpe load failed")
}

func TestUnit_LoadCL100kDefinition_LoaderError(t *testing.T) {
	_, err := loadCL100kDefinition(failBpeLoader{})
	require.Error(t, err)
	require.Contains(t, err.Error(), "bpe load failed")
}

func TestUnit_LoadO200kDefinition_LoaderError(t *testing.T) {
	_, err := loadO200kDefinition(failBpeLoader{})
	require.Error(t, err)
}

func TestUnit_LoadEncoding_DefinitionError(t *testing.T) {
	_, err := loadEncoding(tiktoken.MODEL_CL100K_BASE, failBpeLoader{})
	require.Error(t, err)
}
