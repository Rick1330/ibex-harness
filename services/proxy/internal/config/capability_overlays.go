package config

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const (
	maxCapabilityOverlayJSONBytes = 64 * 1024
	maxCapabilityOverlayEntries   = 64
)

// overlayWire is the strict JSON shape for IBEX_MODEL_CAPABILITY_OVERLAYS.
// Pointer bools require explicit presence so omitted fields fail closed.
type overlayWire struct {
	ModelID           string `json:"model_id"`
	Provider          string `json:"provider"`
	ContextWindow     int    `json:"context_window"`
	MaxOutputTokens   int    `json:"max_output_tokens"`
	SupportsTools     *bool  `json:"supports_tools"`
	SupportsVision    *bool  `json:"supports_vision"`
	SupportsStreaming *bool  `json:"supports_streaming"`
	TokenizerFamily   string `json:"tokenizer_family"`
}

// ParseCapabilityOverlays decodes IBEX_MODEL_CAPABILITY_OVERLAYS JSON.
// Empty input yields a nil slice. Rejects unknown JSON fields, omitted feature
// flags, duplicate model IDs, and rows that fail provider.ValidateCapability.
func ParseCapabilityOverlays(raw string) ([]provider.ModelCapability, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	wires, err := decodeOverlayWires(raw)
	if err != nil {
		return nil, err
	}
	return materializeOverlays(wires)
}

func decodeOverlayWires(raw string) ([]overlayWire, error) {
	if len(raw) > maxCapabilityOverlayJSONBytes {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS exceeds %d bytes", maxCapabilityOverlayJSONBytes)
	}
	dec := json.NewDecoder(bytes.NewReader([]byte(raw)))
	dec.DisallowUnknownFields()
	var wires []overlayWire
	if err := dec.Decode(&wires); err != nil {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: invalid JSON: %w", err)
	}
	if wires == nil {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: expected a JSON array")
	}
	if len(wires) > maxCapabilityOverlayEntries {
		return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS: at most %d entries", maxCapabilityOverlayEntries)
	}
	return wires, nil
}

func materializeOverlays(wires []overlayWire) ([]provider.ModelCapability, error) {
	out := make([]provider.ModelCapability, 0, len(wires))
	seen := make(map[string]struct{}, len(wires))
	for i, wire := range wires {
		cap, err := overlayWireToCapability(wire)
		if err != nil {
			return nil, fmt.Errorf("IBEX_MODEL_CAPABILITY_OVERLAYS[%d]: %w", i, err)
		}
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

func overlayWireToCapability(wire overlayWire) (provider.ModelCapability, error) {
	if err := requireOverlayBools(wire); err != nil {
		return provider.ModelCapability{}, err
	}
	return provider.ModelCapability{
		ModelID:           strings.TrimSpace(wire.ModelID),
		Provider:          strings.TrimSpace(wire.Provider),
		ContextWindow:     wire.ContextWindow,
		MaxOutputTokens:   wire.MaxOutputTokens,
		SupportsTools:     *wire.SupportsTools,
		SupportsVision:    *wire.SupportsVision,
		SupportsStreaming: *wire.SupportsStreaming,
		TokenizerFamily:   strings.TrimSpace(wire.TokenizerFamily),
	}, nil
}

func requireOverlayBools(wire overlayWire) error {
	switch {
	case wire.SupportsTools == nil:
		return fmt.Errorf("supports_tools is required")
	case wire.SupportsVision == nil:
		return fmt.Errorf("supports_vision is required")
	case wire.SupportsStreaming == nil:
		return fmt.Errorf("supports_streaming is required")
	default:
		return nil
	}
}
