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
	schemaVersion   = 1
	sourceLabel     = "packages/provider.BuiltInCapabilityCatalog"
	catalogFileName = "model_capabilities.v1.json"
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
	outPath, checkPath, code := parseExportArgs(args, stderr)
	if code != 0 {
		return code
	}

	doc := buildExport(provider.BuiltInCapabilityCatalog())
	raw, err := marshalCanonical(doc)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: marshal: %v\n", err)
		return 2
	}

	switch {
	case checkPath != "":
		return checkFresh(checkPath, raw, stderr)
	case outPath != "":
		return writeExportFile(outPath, raw, len(doc.Models), stderr)
	default:
		return writeExportStdout(stdout, stderr, raw)
	}
}

func parseExportArgs(args []string, stderr io.Writer) (outPath, checkPath string, code int) {
	fs := flag.NewFlagSet("export_capabilities", flag.ContinueOnError)
	fs.SetOutput(stderr)
	out := fs.String("o", "", "write JSON to this path (default: stdout)")
	check := fs.String("check", "", "exit 1 if committed JSON at path differs from freshly generated export")
	if err := fs.Parse(args); err != nil {
		return "", "", 2
	}
	if *out != "" && *check != "" {
		_, _ = fmt.Fprintln(stderr, "export_capabilities: use -o or -check, not both")
		return "", "", 2
	}
	return *out, *check, 0
}

func writeExportFile(path string, raw []byte, modelCount int, stderr io.Writer) int {
	resolved, err := resolveCatalogPath(path)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: path: %v\n", err)
		return 2
	}
	if err := writeAtomic(resolved, raw, 0o644); err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: write %s: %v\n", resolved, err)
		return 2
	}
	_, _ = fmt.Fprintf(stderr, "wrote %s (%d models)\n", resolved, modelCount)
	return 0
}

func writeExportStdout(stdout, stderr io.Writer, raw []byte) int {
	n, err := stdout.Write(raw)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: stdout write: %v\n", err)
		return 2
	}
	if n != len(raw) {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: short stdout write: %d/%d\n", n, len(raw))
		return 2
	}
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

// resolveCatalogPath requires the leaf name model_capabilities.v1.json and returns
// an absolute cleaned path so CLI -o/-check cannot be used as an open-ended file API.
func resolveCatalogPath(path string) (string, error) {
	trimmed := filepath.Clean(path)
	if trimmed == "." || trimmed == "" {
		return "", fmt.Errorf("empty path")
	}
	if filepath.Base(trimmed) != catalogFileName {
		return "", fmt.Errorf("path must end with %s", catalogFileName)
	}
	abs, err := filepath.Abs(trimmed)
	if err != nil {
		return "", err
	}
	if filepath.Base(abs) != catalogFileName {
		return "", fmt.Errorf("path must end with %s", catalogFileName)
	}
	return abs, nil
}

func writeAtomic(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)
	if dir == "" {
		dir = "."
	}
	tmp, err := os.CreateTemp(dir, ".model_capabilities.*.tmp")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.Remove(tmpName)
		}
	}()
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Chmod(tmpName, perm); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	cleanup = false
	return nil
}

func checkFresh(committedPath string, fresh []byte, stderr io.Writer) int {
	resolved, err := resolveCatalogPath(committedPath)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: path: %v\n", err)
		return 2
	}
	committed, err := os.ReadFile(resolved) // #nosec G304 -- path constrained by resolveCatalogPath
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "export_capabilities: read %s: %v\n", resolved, err)
		return 2
	}
	if bytes.Equal(normalizeNewline(committed), normalizeNewline(fresh)) {
		_, _ = fmt.Fprintf(stderr, "OK: %s matches BuiltInCapabilityCatalog export\n", filepath.Base(resolved))
		return 0
	}
	_, _ = fmt.Fprintf(
		stderr,
		"export_capabilities: %s is stale — run:\n  go run ./packages/provider/scripts/export_capabilities -o %s\n",
		resolved,
		resolved,
	)
	return 1
}

func normalizeNewline(b []byte) []byte {
	return bytes.ReplaceAll(b, []byte("\r\n"), []byte("\n"))
}
