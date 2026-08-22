package tokenizer

import (
	"context"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/Rick1330/ibex-harness/packages/provider"
	tiktoken "github.com/pkoukk/tiktoken-go"
)

type tiktokenBackend struct {
	family string
	enc    string
	loader tiktoken.BpeLoader
	once   sync.Once
	tke    *tiktoken.Tiktoken
	err    error
}

func newTiktokenBackend(family, encoding string, loader tiktoken.BpeLoader) *tiktokenBackend {
	return &tiktokenBackend{family: family, enc: encoding, loader: loader}
}

func (t *tiktokenBackend) Family() string { return t.family }

func (t *tiktokenBackend) IsEstimate() bool { return false }

func (t *tiktokenBackend) Count(ctx context.Context, text string) (int, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if err := validateCountInput(text); err != nil {
		return 0, err
	}
	if text == "" {
		return 0, nil
	}
	tke, err := t.load()
	if err != nil {
		return 0, err
	}
	return len(tke.Encode(text, nil, nil)), nil
}

func (t *tiktokenBackend) load() (*tiktoken.Tiktoken, error) {
	t.once.Do(func() {
		t.tke, t.err = loadEncoding(t.enc, t.loader)
	})
	return t.tke, t.err
}

// NewLocalRegistry builds a registry with bundled OpenAI tiktoken backends and
// the claude estimate backend. assetDir overrides BPE files when present.
func NewLocalRegistry(assetDir string) (*Registry, error) {
	assetDir = strings.TrimSpace(assetDir)
	if assetDir != "" {
		if err := validateAssetDir(assetDir); err != nil {
			return nil, err
		}
	}
	loader := newBundledBpeLoader(assetDir)
	families := map[string]Tokenizer{
		provider.TokenizerFamilyO200kBase:  newTiktokenBackend(provider.TokenizerFamilyO200kBase, tiktoken.MODEL_O200K_BASE, loader),
		provider.TokenizerFamilyCL100kBase: newTiktokenBackend(provider.TokenizerFamilyCL100kBase, tiktoken.MODEL_CL100K_BASE, loader),
		provider.TokenizerFamilyClaude:     newClaudeEstimate(),
	}
	reg, err := NewRegistry(families)
	if err != nil {
		return nil, err
	}
	if err := warmupExactBackends(reg); err != nil {
		return nil, fmt.Errorf("tokenizer warmup: %w", err)
	}
	return reg, nil
}

func validateAssetDir(assetDir string) error {
	root, err := filepath.Abs(filepath.Clean(assetDir))
	if err != nil {
		return fmt.Errorf("IBEX_TOKENIZER_ASSET_DIR: %w", err)
	}
	info, err := os.Stat(root)
	if err != nil {
		return fmt.Errorf("IBEX_TOKENIZER_ASSET_DIR: %w", err)
	}
	if !info.IsDir() {
		return fmt.Errorf("IBEX_TOKENIZER_ASSET_DIR: not a directory")
	}
	if _, err := fs.ReadDir(os.DirFS(root), "."); err != nil {
		return fmt.Errorf("IBEX_TOKENIZER_ASSET_DIR: %w", err)
	}
	return nil
}

func warmupExactBackends(reg *Registry) error {
	ctx := context.Background()
	for _, family := range []string{
		provider.TokenizerFamilyO200kBase,
		provider.TokenizerFamilyCL100kBase,
	} {
		tok, err := reg.ForFamily(family)
		if err != nil {
			return err
		}
		if _, err := tok.Count(ctx, "warmup"); err != nil {
			return fmt.Errorf("family %q: %w", family, err)
		}
	}
	return nil
}

// SelfTestVector is a known-good count used by readiness probes.
type SelfTestVector struct {
	Family string
	Text   string
	Want   int
}

// DefaultSelfTestVectors returns sample counts verified in vectors_test.go.
func DefaultSelfTestVectors() []SelfTestVector {
	return []SelfTestVector{
		{Family: provider.TokenizerFamilyO200kBase, Text: vectorHelloWorld, Want: 2},
		{Family: provider.TokenizerFamilyCL100kBase, Text: vectorHelloWorld, Want: 2},
		{Family: provider.TokenizerFamilyClaude, Text: vectorHelloWorld, Want: 4},
	}
}

// RunSelfTest verifies sample vectors against the registry.
func RunSelfTest(reg *Registry, vectors []SelfTestVector) error {
	if reg == nil {
		return fmt.Errorf("tokenizer registry is nil")
	}
	if len(vectors) == 0 {
		return fmt.Errorf("tokenizer self-test: no vectors")
	}
	ctx := context.Background()
	for _, v := range vectors {
		if err := verifySelfTestVector(reg, ctx, v); err != nil {
			return err
		}
	}
	return nil
}

func verifySelfTestVector(reg *Registry, ctx context.Context, v SelfTestVector) error {
	if strings.TrimSpace(v.Family) == "" {
		return fmt.Errorf("tokenizer self-test: empty family")
	}
	tok, err := reg.ForFamily(v.Family)
	if err != nil {
		return fmt.Errorf("family %q self-test: %w", v.Family, err)
	}
	got, err := tok.Count(ctx, v.Text)
	if err != nil {
		return fmt.Errorf("family %q self-test: %w", v.Family, err)
	}
	if got != v.Want {
		return fmt.Errorf("family %q self-test: got %d want %d", v.Family, got, v.Want)
	}
	return nil
}

func validateCountInput(text string) error {
	if len(text) > MaxCountTextBytes {
		return fmt.Errorf("%w: %d bytes (max %d)", ErrTextTooLong, len(text), MaxCountTextBytes)
	}
	return nil
}
