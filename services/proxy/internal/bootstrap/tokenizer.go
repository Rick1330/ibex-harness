package bootstrap

import (
	"context"
	"fmt"

	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/tokenizer"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func buildTokenizerRegistry(cfg config.Config) (*tokenizer.Registry, error) {
	mode := cfg.Tokenizer.Mode
	switch mode {
	case "local", "":
		return buildLocalTokenizerRegistry(cfg)
	default:
		return nil, fmt.Errorf("tokenizer registry: unsupported IBEX_TOKENIZER_MODE %q", mode)
	}
}

func buildLocalTokenizerRegistry(cfg config.Config) (*tokenizer.Registry, error) {
	reg, err := tokenizer.NewLocalRegistry(tokenizer.LocalRegistryConfig{AssetDir: cfg.Tokenizer.AssetDir})
	if err != nil {
		return nil, fmt.Errorf("tokenizer registry: %w", err)
	}
	catalog, err := capabilityCatalog(cfg)
	if err != nil {
		return nil, fmt.Errorf("tokenizer registry: %w", err)
	}
	if err := tokenizer.ValidateCatalogCoverage(catalog, reg); err != nil {
		return nil, fmt.Errorf("tokenizer registry: %w", err)
	}
	return reg, nil
}

func newTokenizerReadyChecker(reg *tokenizer.Registry) func(context.Context) error {
	return func(ctx context.Context) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		return tokenizer.RunSelfTest(reg, tokenizer.DefaultSelfTestVectors())
	}
}

// countForBuiltinModel is a diagnostics helper for joint bootstrap tests.
func countForBuiltinModel(reg *tokenizer.Registry, model, text string) (int, error) {
	return tokenizer.CountForModel(context.Background(), tokenizer.ModelCountRequest{
		Catalog: provider.BuiltInCapabilityCatalog(),
		Reg:     reg,
		Model:   model,
		Text:    text,
	})
}
