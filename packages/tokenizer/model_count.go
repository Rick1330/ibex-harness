package tokenizer

import (
	"context"
	"fmt"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// ModelCountRequest groups inputs for CountForModel.
type ModelCountRequest struct {
	Catalog provider.CapabilityCatalog
	Reg     *Registry
	Model   string
	Text    string
}

// CountForModel resolves model → capability → family → Count.
func CountForModel(ctx context.Context, req ModelCountRequest) (int, error) {
	return countForModel(ctx, req)
}

func countForModel(ctx context.Context, req ModelCountRequest) (int, error) {
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if req.Reg == nil {
		return 0, fmt.Errorf("%w: registry is nil", ErrMissingTokenizer)
	}
	model := strings.TrimSpace(req.Model)
	if model == "" {
		return 0, fmt.Errorf("%w: empty model id", ErrModelNotInCatalog)
	}
	cap, ok := req.Catalog.Lookup(model)
	if !ok {
		return 0, fmt.Errorf("%w: %q", ErrModelNotInCatalog, model)
	}
	family := strings.TrimSpace(cap.TokenizerFamily)
	if family == provider.TokenizerFamilyUnknown {
		return 0, fmt.Errorf("%w: model %q uses unknown tokenizer family", ErrMissingTokenizer, model)
	}
	tok, err := req.Reg.ForFamily(family)
	if err != nil {
		return 0, fmt.Errorf("%w: model %q requires %q", ErrMissingTokenizer, model, family)
	}
	return tok.Count(ctx, req.Text)
}
