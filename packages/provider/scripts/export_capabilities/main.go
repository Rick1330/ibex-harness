// Command export_capabilities serializes BuiltInCapabilityCatalog (+ tokenizer
// family estimate policy) to the committed generate-and-diff JSON artifact used
// by services/context (ADR-0067 / milestone 3.5.C.1).
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const (
	schemaVersion = 1
	sourceLabel   = "packages/provider.BuiltInCapabilityCatalog"
)

// exitFunc is swapped in tests so main can be exercised without os.Exit.
var exitFunc = os.Exit

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

func main() {
	exitFunc(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("export_capabilities", flag.ContinueOnError)
	fs.SetOutput(stderr)
	outPath := fs.String("o", "", "write JSON to this path (default: stdout)")
	checkPath := fs.String("check", "", "exit 1 if committed JSON at path differs from freshly generated export")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *outPath != "" && *checkPath != "" {
		fmt.Fprintln(stderr, "export_capabilities: use -o or -check, not both")
		return 2
	}

	doc := buildExport(provider.BuiltInCapabilityCatalog())
	raw, err := marshalCanonical(doc)
	if err != nil {
		fmt.Fprintf(stderr, "export_capabilities: marshal: %v\n", err)
		return 2
	}

	if *checkPath != "" {
		return checkFresh(*checkPath, raw, stderr)
	}
	if *outPath != "" {
		if err := os.WriteFile(*outPath, raw, 0o644); err != nil {
			fmt.Fprintf(stderr, "export_capabilities: write %s: %v\n", *outPath, err)
			return 2
		}
		fmt.Fprintf(stderr, "wrote %s (%d models)\n", *outPath, len(doc.Models))
		return 0
	}
	_, _ = stdout.Write(raw)
	return 0
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

func marshalCanonical(doc exportDoc) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(doc); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func checkFresh(committedPath string, fresh []byte, stderr io.Writer) int {
	committed, err := os.ReadFile(committedPath) // NOSONAR — maintainer path from CLI
	if err != nil {
		fmt.Fprintf(stderr, "export_capabilities: read %s: %v\n", committedPath, err)
		return 2
	}
	if bytes.Equal(normalizeNewline(committed), normalizeNewline(fresh)) {
		fmt.Fprintf(stderr, "OK: %s matches BuiltInCapabilityCatalog export\n", filepath.Base(committedPath))
		return 0
	}
	fmt.Fprintf(
		stderr,
		"export_capabilities: %s is stale — run:\n  go run ./packages/provider/scripts/export_capabilities -o %s\n",
		committedPath,
		committedPath,
	)
	return 1
}

func normalizeNewline(b []byte) []byte {
	return bytes.ReplaceAll(b, []byte("\r\n"), []byte("\n"))
}
