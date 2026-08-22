package tokenizer

import "context"

// Tokenizer counts tokens for a single TokenizerFamily (ADR-0041 / ADR-0043).
// Implementations must be goroutine-safe after construction.
type Tokenizer interface {
	Family() string
	Count(ctx context.Context, text string) (int, error)
}

// Estimator marks tokenizers that return documented approximations rather than
// vendor-exact counts (e.g. claude until a local vocab lands).
type Estimator interface {
	IsEstimate() bool
}
