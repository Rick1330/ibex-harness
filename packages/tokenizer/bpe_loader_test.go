package tokenizer

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/stretchr/testify/require"
)

func testAssetDir(path string) assetDirPath     { return assetDirPath(path) }
func testAssetBase(name string) assetBasename   { return assetBasename(name) }
func testVocabText(content string) bpeVocabText { return bpeVocabText([]byte(content)) }

func TestUnit_BpeLoader_AssetDirOverride(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, "o200k_base.tiktoken"), embeddedO200kBPE, 0o600))

	reg, err := NewLocalRegistry(LocalRegistryConfig{AssetDir: dir})
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	n, err := tok.Count(context.Background(), vectorHelloWorld)
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_ReadBoundedFSFile_RejectsOversized(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, "large.tiktoken"), make([]byte, maxBpeAssetBytes+1), 0o600))
	_, err := readBoundedFSFile(os.DirFS(dir), testAssetBase("large.tiktoken"), maxBpeAssetBytes)
	require.Error(t, err)
	require.Contains(t, err.Error(), "exceeds")
}

func TestUnit_LoadBpeFromAssetDir_NonDirectoryRoot(t *testing.T) {
	path := filepath.Join(t.TempDir(), "not-a-dir")
	require.NoError(t, os.WriteFile(path, []byte("x"), 0o600))
	_, _, err := loadBpeFromAssetDir(testAssetDir(path), testAssetBase("o200k_base.tiktoken"))
	require.Error(t, err)
}

func TestUnit_ParseBpeLines_LineErrorIncludesNumber(t *testing.T) {
	_, err := parseBpeLines(testVocabText("YQ== 0\n!!! 1\n"))
	require.Error(t, err)
	require.Contains(t, err.Error(), "line 2:")
}

func TestUnit_ParseBpeLine_RejectsMalformedLine(t *testing.T) {
	_, err := parseBpeLine(bpeLineText("only-one-field"))
	require.ErrorIs(t, err, errInvalidBpeLine)
	_, err = parseBpeLine(bpeLineText("!!! 0"))
	require.Error(t, err)
	_, err = parseBpeLine(bpeLineText("YQ== not-a-rank"))
	require.Error(t, err)
}

func TestUnit_LoadBpeFromAssetDir_RejectsCorruptOverride(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, "o200k_base.tiktoken"), []byte("bad"), 0o600))
	_, found, err := loadBpeFromAssetDir(testAssetDir(dir), testAssetBase("o200k_base.tiktoken"))
	require.True(t, found)
	require.Error(t, err)
}

func TestUnit_ParseBpeLines_MalformedCases(t *testing.T) {
	cases := []struct {
		name    string
		content string
	}{
		{name: "empty", content: ""},
		{name: "duplicate token", content: "YQ== 0\nYQ== 1\n"},
		{name: "duplicate rank", content: "YQ== 0\nYg== 0\n"},
		{name: "negative rank", content: "YQ== -1\n"},
		{name: "non contiguous", content: "YQ== 0\nYg== 2\n"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := parseBpeLines(testVocabText(tc.content))
			require.Error(t, err)
		})
	}
}

func TestUnit_ParseBpeLines_ValidContiguous(t *testing.T) {
	ranks, err := parseBpeLines(testVocabText("YQ== 0\nYg== 1\n"))
	require.NoError(t, err)
	require.Len(t, ranks, 2)
}

func TestUnit_Registry_Families(t *testing.T) {
	reg, err := NewLocalRegistry(LocalRegistryConfig{})
	require.NoError(t, err)
	require.Equal(t, []string{
		provider.TokenizerFamilyCL100kBase,
		provider.TokenizerFamilyClaude,
		provider.TokenizerFamilyO200kBase,
	}, reg.Families())
}

func TestUnit_TiktokenBackend_IsEstimateFalse(t *testing.T) {
	var tok Tokenizer = newTiktokenBackend(tiktokenBackendSpec{
		family: provider.TokenizerFamilyO200kBase, encoding: "o200k_base",
		loader: newBundledBpeLoader(assetDirPath("")),
	})
	est, ok := tok.(Estimator)
	require.True(t, ok)
	require.False(t, est.IsEstimate())
}

func TestUnit_EstimateClaudeTokens(t *testing.T) {
	require.Equal(t, 4, EstimateClaudeTokens(vectorHelloWorld))
}

func TestUnit_ValidateAssetDir_NotDirectory(t *testing.T) {
	path := filepath.Join(t.TempDir(), "file")
	require.NoError(t, os.WriteFile(path, []byte("x"), 0o600))
	require.Error(t, validateAssetDir(testAssetDir(path)))
}

func TestUnit_ValidateAssetDir_Missing(t *testing.T) {
	require.Error(t, validateAssetDir(testAssetDir(filepath.Join(t.TempDir(), "missing"))))
}
