package tokenizer

import (
	"context"
	"os"
	"path/filepath"
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

func TestUnit_CountWithObserver_NilObserver(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	n, err := CountWithObserver(context.Background(), tok, "Hello world", nil)
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_CountForModelWithObserver_ErrorPaths(t *testing.T) {
	obs := &stubObserver{}
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)

	_, err = CountForModelWithObserver(context.Background(), provider.BuiltInCapabilityCatalog(), nil, "gpt-4o", "x", obs)
	require.Error(t, err)
	require.Len(t, obs.calls, 1)
	require.Equal(t, "unknown", obs.calls[0].family)
	require.Equal(t, "error", obs.calls[0].result)

	_, err = CountForModelWithObserver(context.Background(), provider.BuiltInCapabilityCatalog(), reg, "missing", "x", obs)
	require.Error(t, err)
	require.GreaterOrEqual(t, len(obs.calls), 2)
}

func TestUnit_ValidateAssetDir_NotDirectory(t *testing.T) {
	path := filepath.Join(t.TempDir(), "file")
	require.NoError(t, os.WriteFile(path, []byte("x"), 0o600))
	require.Error(t, validateAssetDir(path))
}

func TestUnit_ValidateAssetDir_Missing(t *testing.T) {
	require.Error(t, validateAssetDir(filepath.Join(t.TempDir(), "missing")))
}
