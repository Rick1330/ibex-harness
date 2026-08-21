package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const defaultLiteLLMURL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

type liteLLMEntry struct {
	MaxInputTokens  *float64 `json:"max_input_tokens"`
	MaxOutputTokens *float64 `json:"max_output_tokens"`
	MaxTokens       *float64 `json:"max_tokens"`
}

type modelDiffInput struct {
	id      string
	cap     provider.ModelCapability
	entry   liteLLMEntry
	present bool
	stdout  io.Writer
}

// exitFunc is swapped in tests so main can be exercised without terminating the process.
var exitFunc = os.Exit

func main() {
	exitFunc(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("diff_capabilities", flag.ContinueOnError)
	fs.SetOutput(stderr)
	file := fs.String("file", "", "path to LiteLLM JSON snapshot")
	fetch := fs.Bool("fetch", false, "fetch LiteLLM JSON from GitHub")
	if err := fs.Parse(args); err != nil {
		return 2
	}

	raw, err := loadLiteLLM(*file, *fetch)
	if err != nil {
		writef(stderr, "diff_capabilities: %v\n", err)
		return 2
	}

	var table map[string]liteLLMEntry
	if err := json.Unmarshal(raw, &table); err != nil {
		writef(stderr, "diff_capabilities: parse JSON: %v\n", err)
		return 2
	}

	mismatches := diffCatalog(provider.BuiltInCapabilityCatalog(), table, stdout)
	if mismatches == 0 {
		writeln(stdout, "OK: curated models match LiteLLM context/max_output where present")
		return 0
	}
	writef(stderr, "diff_capabilities: %d mismatch(es)\n", mismatches)
	return 1
}

func diffCatalog(catalog provider.CapabilityCatalog, table map[string]liteLLMEntry, stdout io.Writer) int {
	ids := make([]string, 0, len(catalog))
	for id := range catalog {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	mismatches := 0
	for _, id := range ids {
		entry, ok := table[id]
		mismatches += diffOneModel(modelDiffInput{
			id: id, cap: catalog[id], entry: entry, present: ok, stdout: stdout,
		})
	}
	return mismatches
}

func diffOneModel(in modelDiffInput) int {
	if !in.present {
		writef(in.stdout, "MISSING_UPSTREAM\t%s\t(curated ctx=%d max_out=%d)\n",
			in.id, in.cap.ContextWindow, in.cap.MaxOutputTokens)
		return 1
	}
	upCtx, ctxInvalid := parseUpstreamLimit(in.entry.MaxInputTokens)
	upOut, outInvalid := parseUpstreamLimit(in.entry.MaxOutputTokens)
	if ctxInvalid || outInvalid {
		return reportInvalidUpstreamLimits(in, ctxInvalid, outInvalid)
	}
	// Do not fall back to max_tokens: LiteLLM often uses it for output limits.
	if upCtx == 0 && upOut == 0 {
		writef(in.stdout, "NO_LIMITS_UPSTREAM\t%s\n", in.id)
		return 1
	}
	return countLimitMismatches(in, upCtx, upOut)
}

func reportInvalidUpstreamLimits(in modelDiffInput, ctxInvalid, outInvalid bool) int {
	n := 0
	if ctxInvalid {
		writef(in.stdout, "INVALID_UPSTREAM_CONTEXT\t%s\n", in.id)
		n++
	}
	if outInvalid {
		writef(in.stdout, "INVALID_UPSTREAM_MAX_OUT\t%s\n", in.id)
		n++
	}
	return n
}

func countLimitMismatches(in modelDiffInput, upCtx, upOut int) int {
	n := 0
	if upCtx != 0 && upCtx != in.cap.ContextWindow {
		writef(in.stdout, "CONTEXT_MISMATCH\t%s\tcurated=%d\tlitellm=%d\n", in.id, in.cap.ContextWindow, upCtx)
		n++
	}
	if upOut != 0 && upOut != in.cap.MaxOutputTokens {
		writef(in.stdout, "MAX_OUT_MISMATCH\t%s\tcurated=%d\tlitellm=%d\n", in.id, in.cap.MaxOutputTokens, upOut)
		n++
	}
	return n
}

func loadLiteLLM(file string, fetch bool) ([]byte, error) {
	return loadLiteLLMFrom(file, fetch, defaultLiteLLMURL)
}

func loadLiteLLMFrom(file string, fetch bool, url string) ([]byte, error) {
	switch {
	case strings.TrimSpace(file) != "":
		return os.ReadFile(file)
	case fetch:
		client := &http.Client{Timeout: 30 * time.Second}
		resp, err := client.Get(url)
		if err != nil {
			return nil, err
		}
		defer func() { _ = resp.Body.Close() }()
		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("fetch %s: status %d", url, resp.StatusCode)
		}
		return io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	default:
		return nil, fmt.Errorf("provide -file PATH or -fetch")
	}
}

// parseUpstreamLimit converts a LiteLLM numeric limit. nil and 0 mean absent
// (preserve NO_LIMITS_UPSTREAM). Present values that are fractional, non-positive,
// or outside the int range (including float precision loss) are invalid.
func parseUpstreamLimit(v *float64) (int, bool) {
	if v == nil {
		return 0, false
	}
	f := *v
	if f == 0 {
		return 0, false
	}
	if f < 1 || f != math.Trunc(f) || f > float64(math.MaxInt) {
		return 0, true
	}
	n := int(f)
	if float64(n) != f {
		return 0, true
	}
	return n, false
}

// writef / writeln keep CLI I/O errcheck-clean; a broken stdout/stderr is non-actionable here.
func writef(w io.Writer, format string, args ...any) {
	_, _ = fmt.Fprintf(w, format, args...)
}

func writeln(w io.Writer, s string) {
	_, _ = fmt.Fprintln(w, s)
}
