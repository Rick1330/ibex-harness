package tokenizer

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
	tiktoken_loader "github.com/pkoukk/tiktoken-go-loader"
	"github.com/stretchr/testify/require"
)

func TestUnit_JailedAssetPath_RejectsTraversal(t *testing.T) {
	_, err := jailedAssetPath(t.TempDir(), "../outside.tiktoken")
	require.ErrorIs(t, err, ErrAssetPathEscape)
}

func TestUnit_JailedAssetPath_RejectsNestedBase(t *testing.T) {
	_, err := jailedAssetPath(t.TempDir(), "../etc/passwd")
	require.ErrorIs(t, err, ErrAssetPathEscape)
}

func TestUnit_BpeLoader_CorruptAssetDirFailsStartup(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, "o200k_base.tiktoken"), []byte("not-bpe"), 0o600))
	_, err := NewLocalRegistry(dir)
	require.Error(t, err)
	require.Contains(t, err.Error(), "warmup")
}

func TestUnit_BpeLoader_MissingAssetDirFallsBackToEmbedded(t *testing.T) {
	dir := t.TempDir()
	reg, err := NewLocalRegistry(dir)
	require.NoError(t, err)
	tok, err := reg.ForFamily(provider.TokenizerFamilyO200kBase)
	require.NoError(t, err)
	n, err := tok.Count(context.Background(), "Hello world")
	require.NoError(t, err)
	require.Equal(t, 2, n)
}

func TestUnit_BpeLoader_AssetDirPermissionDenied(t *testing.T) {
	if os.Getuid() == 0 {
		t.Skip("root can read chmod 000 files on Linux")
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "o200k_base.tiktoken")
	require.NoError(t, os.WriteFile(path, []byte("bad"), 0o000))
	t.Cleanup(func() { _ = os.Chmod(path, 0o600) })
	_, err := NewLocalRegistry(dir)
	require.Error(t, err)
}

func TestUnit_CountForModel_NilRegistry(t *testing.T) {
	_, err := CountForModel(context.Background(), provider.BuiltInCapabilityCatalog(), nil, "gpt-4o", "x")
	require.ErrorIs(t, err, ErrMissingTokenizer)
}

func TestUnit_CountForModel_EmptyModel(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	_, err = CountForModel(context.Background(), provider.BuiltInCapabilityCatalog(), reg, "  ", "x")
	require.ErrorIs(t, err, ErrModelNotInCatalog)
}

func TestUnit_CountForModel_NilContextDone(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = CountForModel(ctx, provider.BuiltInCapabilityCatalog(), reg, "gpt-4o", "x")
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_RunSelfTest_EmptyVectors(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	require.Error(t, RunSelfTest(reg, nil))
}

func TestUnit_RunSelfTest_EmptyFamily(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	err = RunSelfTest(reg, []SelfTestVector{{Family: " ", Text: "x", Want: 1}})
	require.Error(t, err)
}

func TestUnit_ForFamily_UnknownAndEmpty(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	_, err = reg.ForFamily("not-a-family")
	require.ErrorIs(t, err, ErrUnknownFamily)
	_, err = reg.ForFamily("")
	require.ErrorIs(t, err, ErrUnknownFamily)
}

func TestUnit_ConcurrentCount_AllFamilies(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	families := []string{
		provider.TokenizerFamilyO200kBase,
		provider.TokenizerFamilyCL100kBase,
		provider.TokenizerFamilyClaude,
	}
	const workers = 32
	var wg sync.WaitGroup
	errCh := make(chan error, workers*len(families))
	for _, family := range families {
		tok, tokErr := reg.ForFamily(family)
		require.NoError(t, tokErr)
		for i := 0; i < workers; i++ {
			wg.Add(1)
			go func(tok Tokenizer) {
				defer wg.Done()
				_, countErr := tok.Count(context.Background(), "concurrent tokenizer probe")
				errCh <- countErr
			}(tok)
		}
	}
	wg.Wait()
	close(errCh)
	for countErr := range errCh {
		require.NoError(t, countErr)
	}
}

func TestUnit_ConcurrentEncodingLoad(t *testing.T) {
	loader := newBundledBpeLoader("")
	const workers = 8
	errCh := make(chan error, workers*2)
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(2)
		go func() {
			defer wg.Done()
			_, err := loadEncoding("o200k_base", loader)
			errCh <- err
		}()
		go func() {
			defer wg.Done()
			_, err := loadEncoding("cl100k_base", loader)
			errCh <- err
		}()
	}
	wg.Wait()
	close(errCh)
	for err := range errCh {
		require.NoError(t, err)
	}
}

func TestUnit_BpeLoader_OfflineCL100k(t *testing.T) {
	loader := &bundledBpeLoader{offline: tiktoken_loader.NewOfflineLoader()}
	ranks, err := loader.LoadTiktokenBpe("https://example.invalid/cl100k_base.tiktoken")
	require.NoError(t, err)
	require.NotEmpty(t, ranks)
}

func TestUnit_LoadBpeFile_Missing(t *testing.T) {
	_, err := loadBpeFile(filepath.Join(t.TempDir(), "missing.tiktoken"))
	require.Error(t, err)
	require.True(t, errors.Is(err, os.ErrNotExist))
}

func TestUnit_Claude_CountRespectsContext(t *testing.T) {
	tok := newClaudeEstimate()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := tok.Count(ctx, "Hello")
	require.ErrorIs(t, err, context.Canceled)
}

func TestUnit_NewLocalRegistry_RejectsUnreadableAssetDir(t *testing.T) {
	if os.Getuid() == 0 {
		t.Skip("root bypasses directory permission checks")
	}
	dir := t.TempDir()
	require.NoError(t, os.Chmod(dir, 0o000))
	t.Cleanup(func() { _ = os.Chmod(dir, 0o700) })
	_, err := NewLocalRegistry(dir)
	require.Error(t, err)
	require.Contains(t, err.Error(), "IBEX_TOKENIZER_ASSET_DIR")
}

func TestUnit_SelfTestRespectsContext(t *testing.T) {
	reg, err := NewLocalRegistry("")
	require.NoError(t, err)
	checker := func(ctx context.Context) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		return RunSelfTest(reg, DefaultSelfTestVectors())
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	require.NoError(t, checker(ctx))
}
