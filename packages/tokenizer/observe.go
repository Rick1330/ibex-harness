package tokenizer

import (
	"context"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

// CountObserver records tokenizer Count outcomes (optional metrics hook).
type CountObserver interface {
	ObserveTokenizerCount(family, result string, seconds float64)
}

// CountWithObserver runs Count and records duration/outcome when obs is non-nil.
func CountWithObserver(
	ctx context.Context,
	tok Tokenizer,
	text string,
	obs CountObserver,
) (int, error) {
	start := time.Now()
	n, err := tok.Count(ctx, text)
	if obs != nil {
		result := "success"
		if err != nil {
			result = "error"
		}
		obs.ObserveTokenizerCount(tok.Family(), result, time.Since(start).Seconds())
	}
	return n, err
}

// CountForModelWithObserver is CountForModel with optional metrics observation.
func CountForModelWithObserver(
	ctx context.Context,
	catalog provider.CapabilityCatalog,
	reg *Registry,
	model string,
	text string,
	obs CountObserver,
) (int, error) {
	start := time.Now()
	family := observerFamilyLabel(catalog, model)
	n, err := CountForModel(ctx, catalog, reg, model, text)
	if obs == nil {
		return n, err
	}
	result := "success"
	if err != nil {
		result = "error"
	}
	obs.ObserveTokenizerCount(family, result, time.Since(start).Seconds())
	return n, err
}

func observerFamilyLabel(catalog provider.CapabilityCatalog, model string) string {
	cap, ok := catalog.Lookup(strings.TrimSpace(model))
	if !ok {
		return "unknown"
	}
	family := strings.TrimSpace(cap.TokenizerFamily)
	if family == "" || family == provider.TokenizerFamilyUnknown {
		return "unknown"
	}
	return family
}
