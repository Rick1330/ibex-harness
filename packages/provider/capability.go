package provider

import (
	"errors"
	"fmt"
	"strings"
)

// ErrMissingCapability is returned by NewRegistry when a registered model has
// no capability entry in the catalog.
var ErrMissingCapability = errors.New("missing model capability")

// ErrInvalidCapability is returned when a capability row fails validation
// (malformed fields, tokenizer allowlist, ModelID mismatch, etc.).
var ErrInvalidCapability = errors.New("invalid model capability")

// CapabilityProvider* are vendor-family values for ModelCapability.Provider.
const (
	CapabilityProviderOpenAI    = "openai"
	CapabilityProviderAnthropic = "anthropic"
)

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
// entries are skipped. Duplicate IDs: last write wins. Provider and
// TokenizerFamily are trimmed so stored rows match ValidateCapability checks.
func CatalogFromCapabilities(caps ...ModelCapability) CapabilityCatalog {
	out := make(CapabilityCatalog, len(caps))
	for _, cap := range caps {
		id := strings.TrimSpace(cap.ModelID)
		if id == "" {
			continue
		}
		cap.ModelID = id
		cap.Provider = strings.TrimSpace(cap.Provider)
		cap.TokenizerFamily = strings.TrimSpace(cap.TokenizerFamily)
		out[id] = cap
	}
	return out
}

// ValidateCapability checks required fields for a catalog row (overlay-safe).
// TokenizerFamily must be one of the declared family constants (including
// TokenizerFamilyUnknown for ExtraModels overlays).
func ValidateCapability(cap ModelCapability) error {
	return validateCapability(cap, true)
}

// ValidateBuiltinCapability is ValidateCapability plus rejection of
// TokenizerFamilyUnknown (built-in curated rows must name a real family).
func ValidateBuiltinCapability(cap ModelCapability) error {
	return validateCapability(cap, false)
}

func validateCapability(cap ModelCapability, allowUnknownTokenizer bool) error {
	if err := validateCapabilityIdentity(cap); err != nil {
		return err
	}
	if err := validateCapabilityLimits(cap); err != nil {
		return err
	}
	return validateCapabilityTokenizer(cap, allowUnknownTokenizer)
}

func validateCapabilityIdentity(cap ModelCapability) error {
	id := strings.TrimSpace(cap.ModelID)
	if id == "" {
		return fmt.Errorf("%w: empty ModelID", ErrInvalidCapability)
	}
	if cap.ModelID != id {
		return fmt.Errorf("%w: %q: ModelID must not have surrounding whitespace", ErrInvalidCapability, id)
	}
	provider := strings.TrimSpace(cap.Provider)
	if provider == "" {
		return fmt.Errorf("%w: %q: empty Provider", ErrInvalidCapability, id)
	}
	if cap.Provider != provider {
		return fmt.Errorf("%w: %q: Provider must not have surrounding whitespace", ErrInvalidCapability, id)
	}
	if !isAllowedCapabilityProvider(provider) {
		return fmt.Errorf("%w: %q: unsupported Provider %q", ErrInvalidCapability, id, provider)
	}
	return nil
}

func validateCapabilityLimits(cap ModelCapability) error {
	id := strings.TrimSpace(cap.ModelID)
	if cap.ContextWindow <= 0 {
		return fmt.Errorf("%w: %q: ContextWindow must be > 0", ErrInvalidCapability, id)
	}
	if cap.MaxOutputTokens <= 0 {
		return fmt.Errorf("%w: %q: MaxOutputTokens must be > 0", ErrInvalidCapability, id)
	}
	if cap.MaxOutputTokens > cap.ContextWindow {
		return fmt.Errorf("%w: %q: MaxOutputTokens (%d) exceeds ContextWindow (%d)",
			ErrInvalidCapability, id, cap.MaxOutputTokens, cap.ContextWindow)
	}
	return nil
}

func validateCapabilityTokenizer(cap ModelCapability, allowUnknownTokenizer bool) error {
	id := strings.TrimSpace(cap.ModelID)
	family := strings.TrimSpace(cap.TokenizerFamily)
	if family == "" {
		return fmt.Errorf("%w: %q: empty TokenizerFamily", ErrInvalidCapability, id)
	}
	if cap.TokenizerFamily != family {
		return fmt.Errorf("%w: %q: TokenizerFamily must not have surrounding whitespace", ErrInvalidCapability, id)
	}
	if !isAllowedTokenizerFamily(family, allowUnknownTokenizer) {
		return fmt.Errorf("%w: %q: unsupported TokenizerFamily %q", ErrInvalidCapability, id, family)
	}
	return nil
}

func isAllowedCapabilityProvider(provider string) bool {
	switch provider {
	case CapabilityProviderOpenAI, CapabilityProviderAnthropic:
		return true
	default:
		return false
	}
}

func isAllowedTokenizerFamily(family string, allowUnknown bool) bool {
	switch family {
	case TokenizerFamilyO200kBase, TokenizerFamilyCL100kBase, TokenizerFamilyClaude:
		return true
	case TokenizerFamilyUnknown:
		return allowUnknown
	default:
		return false
	}
}
