package config

import (
	"encoding/json"
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const (
	maxCapabilityOverlayJSONBytes = 64 * 1024
	maxCapabilityOverlayEntries   = 64
)

// ParseCapabilityOverlays decodes IBEX_MODEL_CAPABILITY_OVERLAYS JSON.
// Empty input yields a nil slice. Each entry must pass provider.ValidateCapability.
func ParseCapabilityOverlays(raw string) ([]provider.ModelCapability, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	if utf8.RuneCountInString(raw) > maxCapabilityOverlayJSONBytes {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS exceeds %d bytes", maxCapabilityOverlayJSONBytes)
	}
	var caps []provider.ModelCapability
	if err := json.Unmarshal([]byte(raw), &caps); err != nil {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: invalid JSON: %w", err)
	}
	if len(caps) > maxCapabilityOverlayEntries {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: at most %d entries", maxCapabilityOverlayEntries)
	}
	out := make([]provider.ModelCapability, 0, len(caps))
	seen := make(map[string]struct{}, len(caps))
	for i, cap := range caps {
		cap.ModelID = strings.TrimSpace(cap.ModelID)
		cap.Provider = strings.TrimSpace(cap.Provider)
		cap.TokenizerFamily = strings.TrimSpace(cap.TokenizerFamily)
		if err := provider.ValidateCapability(cap); err != nil {
			return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS[%d]: %w", i, err)
		}
		if _, ok := seen[cap.ModelID]; ok {
			return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: duplicate model_id %q", cap.ModelID)
		}
		seen[cap.ModelID] = struct{}{}
		out = append(out, cap)
	}
	return out, nil
}
