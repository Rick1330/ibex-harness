package modelpolicy

import (
	"fmt"
	"path/filepath"
	"strings"
)

// ValidatePattern checks that pattern is a non-empty filepath.Match glob.
func ValidatePattern(pattern string) error {
	p := strings.TrimSpace(pattern)
	if p == "" {
		return fmt.Errorf("modelpolicy: model_pattern is required")
	}
	if len(p) > 256 {
		return fmt.Errorf("modelpolicy: model_pattern exceeds 256 characters")
	}
	if _, err := filepath.Match(p, ""); err != nil {
		return fmt.Errorf("modelpolicy: invalid model_pattern: %w", err)
	}
	return nil
}

// Match reports whether model matches pattern using filepath.Match.
func Match(pattern, model string) (bool, error) {
	if err := ValidatePattern(pattern); err != nil {
		return false, err
	}
	ok, err := filepath.Match(strings.TrimSpace(pattern), model)
	if err != nil {
		return false, fmt.Errorf("modelpolicy: match: %w", err)
	}
	return ok, nil
}
