package billing

import (
	"fmt"
	"math"
	"path"
	"strings"
)

// PriceRow is one rate-card price entry (provider + model glob).
type PriceRow struct {
	Provider         string `json:"provider"`
	ModelPattern     string `json:"model_pattern"`
	InputCentsPer1k  int64  `json:"input_cents_per_1k"`
	OutputCentsPer1k int64  `json:"output_cents_per_1k"`
}

// CardVersion is an immutable published rate-card snapshot used at write time.
type CardVersion struct {
	Version string
	Prices  []PriceRow
}

// TokenUsage is token counts used for cost estimation.
type TokenUsage struct {
	Provider     string
	Model        string
	InputTokens  int64
	OutputTokens int64
}

// EstimateCost freezes estimated cost cents against a published card version.
// Matching uses the first price row whose provider equals (case-insensitive)
// and model_pattern matches via path.Match (shell-style globs).
func EstimateCost(card CardVersion, usage TokenUsage) (cents int64, version string, err error) {
	if strings.TrimSpace(card.Version) == "" {
		return 0, "", fmt.Errorf("billing: rate card version is required")
	}
	row, ok := matchPrice(card.Prices, usage.Provider, usage.Model)
	if !ok {
		return 0, card.Version, fmt.Errorf("billing: no rate for provider=%q model=%q", usage.Provider, usage.Model)
	}
	if usage.InputTokens < 0 || usage.OutputTokens < 0 ||
		row.InputCentsPer1k < 0 || row.OutputCentsPer1k < 0 {
		return 0, "", fmt.Errorf("billing: negative token or price operand")
	}
	in, err := ceilMulDiv1k(usage.InputTokens, row.InputCentsPer1k)
	if err != nil {
		return 0, "", err
	}
	out, err := ceilMulDiv1k(usage.OutputTokens, row.OutputCentsPer1k)
	if err != nil {
		return 0, "", err
	}
	if in > math.MaxInt64-out {
		return 0, "", fmt.Errorf("billing: cost overflow")
	}
	return in + out, card.Version, nil
}

// ceilMulDiv1k computes ceil(tokens * centsPer1k / 1000) with overflow checks.
func ceilMulDiv1k(tokens, centsPer1k int64) (int64, error) {
	if tokens == 0 || centsPer1k == 0 {
		return 0, nil
	}
	if tokens > math.MaxInt64/centsPer1k {
		return 0, fmt.Errorf("billing: cost overflow")
	}
	prod := tokens * centsPer1k
	if prod > math.MaxInt64-999 {
		return 0, fmt.Errorf("billing: cost overflow")
	}
	return (prod + 999) / 1000, nil
}

func matchPrice(prices []PriceRow, provider, model string) (PriceRow, bool) {
	prov := strings.ToLower(strings.TrimSpace(provider))
	mod := strings.TrimSpace(model)
	for _, p := range prices {
		if strings.ToLower(strings.TrimSpace(p.Provider)) != prov {
			continue
		}
		pat := strings.TrimSpace(p.ModelPattern)
		if pat == "" {
			continue
		}
		ok, err := path.Match(pat, mod)
		if err != nil || !ok {
			continue
		}
		return p, true
	}
	return PriceRow{}, false
}
