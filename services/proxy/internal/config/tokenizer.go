package config

import (
	"fmt"
	"strings"
)

const (
	defaultTokenizerMode = "local"
)

// TokenizerConfig holds tokenizer registry settings (ADR-0043).
type TokenizerConfig struct {
	Mode     string
	AssetDir string
}

func (c *Config) applyTokenizerDefaults() {
	c.Tokenizer.Mode = strings.ToLower(strings.TrimSpace(c.Tokenizer.Mode))
	if c.Tokenizer.Mode == "" {
		c.Tokenizer.Mode = defaultTokenizerMode
	}
	c.Tokenizer.AssetDir = strings.TrimSpace(c.Tokenizer.AssetDir)
}

func (c Config) validateTokenizer() error {
	mode := c.Tokenizer.Mode
	switch mode {
	case "local":
		return nil
	case "service", "dual":
		return fmt.Errorf("IBEX_TOKENIZER_MODE=%q is not implemented in 2.5.G2.M1 (use local)", mode)
	default:
		return fmt.Errorf("IBEX_TOKENIZER_MODE must be local, service, or dual")
	}
}
