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

// ModelCountObserveRequest groups inputs for CountForModelWithObserver.
type ModelCountObserveRequest struct {
	ModelCountRequest
	Obs CountObserver
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
	observeCountOutcome(obs, tok.Family(), err, start)
	return n, err
}

// CountForModelWithObserver is CountForModel with optional metrics observation.
func CountForModelWithObserver(req ModelCountObserveRequest) (int, error) {
	return countForModelWithObserver(req)
}

func countForModelWithObserver(req ModelCountObserveRequest) (int, error) {
	start := time.Now()
	family := observerFamilyLabel(req.Catalog, req.Model)
	n, err := countForModel(req.ModelCountRequest)
	if req.Obs == nil {
		return n, err
	}
	req.Obs.ObserveTokenizerCount(family, countResult(err), time.Since(start).Seconds())
	return n, err
}

func observeCountOutcome(obs CountObserver, family string, err error, start time.Time) {
	if obs == nil {
		return
	}
	obs.ObserveTokenizerCount(family, countResult(err), time.Since(start).Seconds())
}

func countResult(err error) string {
	if err != nil {
		return "error"
	}
	return "success"
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
