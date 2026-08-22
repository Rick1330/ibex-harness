package tokenizer

import (
	"context"
	"unicode/utf8"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// claudeCharsPerToken is the documented Anthropic heuristic (~4 characters per
// token). We use rune count with ceil(runes/3.5) for a conservative budget
// estimate until a local Claude vocab is available (ADR-0043).
const claudeRunesPerTokenNumer = 2
const claudeRunesPerTokenDenom = 7 // ceil(runes/3.5) == (runes*2+6)/7

type claudeEstimate struct{}

func newClaudeEstimate() *claudeEstimate { return &claudeEstimate{} }

func (c *claudeEstimate) Family() string { return provider.TokenizerFamilyClaude }

func (c *claudeEstimate) IsEstimate() bool { return true }

func (c *claudeEstimate) Count(ctx context.Context, text string) (int, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if err := validateCountInput(text); err != nil {
		return 0, err
	}
	if text == "" {
		return 0, nil
	}
	runes := utf8.RuneCountInString(text)
	return (runes*claudeRunesPerTokenNumer + claudeRunesPerTokenDenom - 1) / claudeRunesPerTokenDenom, nil
}

// EstimateClaudeTokens exposes the claude estimate formula for vector tests.
func EstimateClaudeTokens(text string) int {
	c := newClaudeEstimate()
	n, _ := c.Count(context.Background(), text)
	return n
}
