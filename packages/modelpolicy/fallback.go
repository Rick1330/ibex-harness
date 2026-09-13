package modelpolicy

import "strings"

// FallbackChainForModel returns the fallback_chain from the first-match allow
// policy for model. Empty / denied / unmatched → nil chain (opt-out).
func FallbackChainForModel(policies []Policy, model string) ([]string, error) {
	dec, err := EvaluatePolicies(policies, model)
	if err != nil {
		return nil, err
	}
	if !dec.Matched || !dec.Allowed || dec.Policy == nil {
		return nil, nil
	}
	return NormalizeFallbackChain(dec.Policy.FallbackChain), nil
}

// TruncateChain returns at most maxDepth entries. maxDepth < 1 is treated as 1.
func TruncateChain(chain []string, maxDepth int) []string {
	if maxDepth < 1 {
		maxDepth = 1
	}
	if len(chain) <= maxDepth {
		return append([]string(nil), chain...)
	}
	return append([]string(nil), chain[:maxDepth]...)
}

// NormalizeFallbackChain trims entries and drops empties. Returns nil when empty.
func NormalizeFallbackChain(chain []string) []string {
	if len(chain) == 0 {
		return nil
	}
	out := make([]string, 0, len(chain))
	for _, raw := range chain {
		m := strings.TrimSpace(raw)
		if m == "" {
			continue
		}
		out = append(out, m)
	}
	if len(out) == 0 {
		return nil
	}
	return out
}
