package tokenizer

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// Registry maps TokenizerFamily keys to implementations (read-only after init).
type Registry struct {
	byFamily map[string]Tokenizer
}

// NewRegistry constructs a registry from family → impl. Returns ErrDuplicateFamily
// when two tokenizers claim the same family key.
func NewRegistry(families map[string]Tokenizer) (*Registry, error) {
	byFamily := make(map[string]Tokenizer, len(families))
	for family, tok := range families {
		key := strings.TrimSpace(family)
		if key == "" {
			return nil, fmt.Errorf("%w: empty family key", ErrUnknownFamily)
		}
		if tok == nil {
			return nil, fmt.Errorf("%w: nil tokenizer for %q", ErrMissingTokenizer, key)
		}
		if got := strings.TrimSpace(tok.Family()); got != key {
			return nil, fmt.Errorf("%w: key %q tokenizers reports %q", ErrUnknownFamily, key, got)
		}
		if _, dup := byFamily[key]; dup {
			return nil, fmt.Errorf("%w: %q", ErrDuplicateFamily, key)
		}
		byFamily[key] = tok
	}
	return &Registry{byFamily: byFamily}, nil
}

// ForFamily returns the tokenizer for family or ErrUnknownFamily.
func (r *Registry) ForFamily(family string) (Tokenizer, error) {
	if r == nil {
		return nil, ErrUnknownFamily
	}
	key := strings.TrimSpace(family)
	tok, ok := r.byFamily[key]
	if !ok {
		return nil, fmt.Errorf("%w: %q", ErrUnknownFamily, key)
	}
	return tok, nil
}

// Families returns sorted family keys present in the registry.
func (r *Registry) Families() []string {
	if r == nil {
		return nil
	}
	out := make([]string, 0, len(r.byFamily))
	for f := range r.byFamily {
		out = append(out, f)
	}
	sort.Strings(out)
	return out
}

// RequiredFamilies returns distinct non-unknown tokenizer families referenced by catalog.
func RequiredFamilies(catalog provider.CapabilityCatalog) []string {
	seen := make(map[string]struct{})
	for _, cap := range catalog {
		family := strings.TrimSpace(cap.TokenizerFamily)
		if family == "" || family == provider.TokenizerFamilyUnknown {
			continue
		}
		seen[family] = struct{}{}
	}
	out := make([]string, 0, len(seen))
	for f := range seen {
		out = append(out, f)
	}
	return out
}

// ValidateCatalogCoverage fails closed when catalog references a non-unknown family
// with no registry implementation.
func ValidateCatalogCoverage(catalog provider.CapabilityCatalog, reg *Registry) error {
	if reg == nil {
		return fmt.Errorf("tokenizer registry is nil")
	}
	for _, family := range RequiredFamilies(catalog) {
		if _, err := reg.ForFamily(family); err != nil {
			return fmt.Errorf("%w: catalog requires %q", ErrMissingTokenizer, family)
		}
	}
	return nil
}

// CountForModel resolves model → capability → family → Count.
func CountForModel(
	ctx context.Context,
	catalog provider.CapabilityCatalog,
	reg *Registry,
	model string,
	text string,
) (int, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if reg == nil {
		return 0, fmt.Errorf("%w: registry is nil", ErrMissingTokenizer)
	}
	model = strings.TrimSpace(model)
	if model == "" {
		return 0, fmt.Errorf("%w: empty model id", ErrModelNotInCatalog)
	}
	cap, ok := catalog.Lookup(model)
	if !ok {
		return 0, fmt.Errorf("%w: %q", ErrModelNotInCatalog, model)
	}
	family := strings.TrimSpace(cap.TokenizerFamily)
	if family == provider.TokenizerFamilyUnknown {
		return 0, fmt.Errorf("%w: model %q uses unknown tokenizer family", ErrMissingTokenizer, model)
	}
	tok, err := reg.ForFamily(family)
	if err != nil {
		return 0, err
	}
	return tok.Count(ctx, text)
}
