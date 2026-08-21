package provider

import (
	"errors"
	"fmt"
	"strings"
)

// ErrMissingCapability is returned by NewRegistry when a registered model has
// no capability entry in the catalog.
var ErrMissingCapability = errors.New("missing model capability")

// Tokenizer family keys consumed by the Phase 2.5.G2 tokenizer registry.
const (
	TokenizerFamilyO200kBase  = "o200k_base"
	TokenizerFamilyCL100kBase = "cl100k_base"
	TokenizerFamilyClaude     = "claude"
	// TokenizerFamilyUnknown is allowed only on explicit ExtraModels overlays,
	// never on built-in curated rows.
	TokenizerFamilyUnknown = "unknown"
)

// ModelCapability describes static per-model limits and feature support.
// Provider is the vendor family for the model ID ("openai", "anthropic"),
// not necessarily the runtime adapter name (mock reuses OpenAI rows).
type ModelCapability struct {
	ModelID           string `json:"model_id"`
	Provider          string `json:"provider"`
	ContextWindow     int    `json:"context_window"`
	MaxOutputTokens   int    `json:"max_output_tokens"`
	SupportsTools     bool   `json:"supports_tools"`
	SupportsVision    bool   `json:"supports_vision"`
	SupportsStreaming bool   `json:"supports_streaming"`
	TokenizerFamily   string `json:"tokenizer_family"`
}

// CapabilityCatalog maps model ID → capability. Lookups are case-sensitive on
// the trimmed model ID used at registration time.
type CapabilityCatalog map[string]ModelCapability

// Lookup returns the capability for model, or (zero, false) if absent.
func (c CapabilityCatalog) Lookup(model string) (ModelCapability, bool) {
	if len(c) == 0 {
		return ModelCapability{}, false
	}
	cap, ok := c[model]
	return cap, ok
}

// MergeCapabilityCatalog returns a new catalog with base entries, then each
// overlay applied in order (later overlays win on ID collision).
func MergeCapabilityCatalog(base CapabilityCatalog, overlays ...CapabilityCatalog) CapabilityCatalog {
	out := make(CapabilityCatalog, len(base))
	for id, cap := range base {
		out[id] = cap
	}
	for _, overlay := range overlays {
		for id, cap := range overlay {
			out[id] = cap
		}
	}
	return out
}

// CatalogFromCapabilities builds a catalog from capability rows. Empty ModelID
// entries are skipped. Duplicate IDs: last write wins.
func CatalogFromCapabilities(caps ...ModelCapability) CapabilityCatalog {
	out := make(CapabilityCatalog, len(caps))
	for _, cap := range caps {
		id := strings.TrimSpace(cap.ModelID)
		if id == "" {
			continue
		}
		cap.ModelID = id
		out[id] = cap
	}
	return out
}

// ValidateCapability checks required fields for a catalog row.
func ValidateCapability(cap ModelCapability) error {
	id := strings.TrimSpace(cap.ModelID)
	if id == "" {
		return fmt.Errorf("model capability: empty ModelID")
	}
	if strings.TrimSpace(cap.Provider) == "" {
		return fmt.Errorf("model capability %q: empty Provider", id)
	}
	if cap.ContextWindow <= 0 {
		return fmt.Errorf("model capability %q: ContextWindow must be > 0", id)
	}
	if cap.MaxOutputTokens <= 0 {
		return fmt.Errorf("model capability %q: MaxOutputTokens must be > 0", id)
	}
	if strings.TrimSpace(cap.TokenizerFamily) == "" {
		return fmt.Errorf("model capability %q: empty TokenizerFamily", id)
	}
	return nil
}
