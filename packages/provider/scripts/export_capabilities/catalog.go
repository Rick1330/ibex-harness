package main

import (
	"bytes"
	"encoding/json"
	"sort"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const (
	schemaVersion   = 1
	sourceLabel     = "packages/provider.BuiltInCapabilityCatalog"
	catalogFileName = "model_capabilities.v1.json"
)

type familyPolicy struct {
	EstimateKind         string  `json:"estimate_kind"`
	SafetyBufferFraction float64 `json:"safety_buffer_fraction"`
}

type exportDoc struct {
	SchemaVersion     int                        `json:"schema_version"`
	Source            string                     `json:"source"`
	Models            []provider.ModelCapability `json:"models"`
	TokenizerFamilies map[string]familyPolicy    `json:"tokenizer_families"`
}

func buildExport(catalog provider.CapabilityCatalog) exportDoc {
	ids := make([]string, 0, len(catalog))
	for id := range catalog {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	models := make([]provider.ModelCapability, 0, len(ids))
	for _, id := range ids {
		models = append(models, catalog[id])
	}
	return exportDoc{
		SchemaVersion:     schemaVersion,
		Source:            sourceLabel,
		Models:            models,
		TokenizerFamilies: tokenizerFamilyPolicies(),
	}
}

func tokenizerFamilyPolicies() map[string]familyPolicy {
	// Keep keys aligned with provider.TokenizerFamily* constants.
	return map[string]familyPolicy{
		provider.TokenizerFamilyO200kBase: {
			EstimateKind:         "chars_div_4",
			SafetyBufferFraction: 0.02,
		},
		provider.TokenizerFamilyCL100kBase: {
			EstimateKind:         "chars_div_4",
			SafetyBufferFraction: 0.02,
		},
		provider.TokenizerFamilyClaude: {
			EstimateKind:         "runes_div_3_5",
			SafetyBufferFraction: 0.05,
		},
		provider.TokenizerFamilyUnknown: {
			EstimateKind:         "chars_div_4",
			SafetyBufferFraction: 0.10,
		},
	}
}

// jsonEncode is swapped in tests to force marshal failure paths.
var jsonEncode = func(enc *json.Encoder, v any) error { return enc.Encode(v) }

func marshalCanonical(doc exportDoc) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := jsonEncode(enc, doc); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func normalizeNewline(b []byte) []byte {
	return bytes.ReplaceAll(b, []byte("\r\n"), []byte("\n"))
}
