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
	if strings.TrimSpace(c.Tokenizer.Mode) == "" {
		c.Tokenizer.Mode = defaultTokenizerMode
	}
}

func (c Config) validateTokenizer() error {
	mode := strings.ToLower(strings.TrimSpace(c.Tokenizer.Mode))
	switch mode {
	case "local":
		return nil
	case "service", "dual":
		return fmt.Errorf("IBEX_TOKENIZER_MODE=%q is not implemented in 2.5.G2 (use local)", mode)
	default:
		return fmt.Errorf("IBEX_TOKENIZER_MODE must be local, service, or dual")
	}
}
