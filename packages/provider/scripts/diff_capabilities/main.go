package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
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

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
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
		fmt.Fprintf(stderr, "diff_capabilities: %v\n", err)
		return 2
	}

	var table map[string]liteLLMEntry
	if err := json.Unmarshal(raw, &table); err != nil {
		fmt.Fprintf(stderr, "diff_capabilities: parse JSON: %v\n", err)
		return 2
	}

	mismatches := diffCatalog(provider.BuiltInCapabilityCatalog(), table, stdout)
	if mismatches == 0 {
		fmt.Fprintln(stdout, "OK: curated models match LiteLLM context/max_output where present")
		return 0
	}
	fmt.Fprintf(stderr, "diff_capabilities: %d mismatch(es)\n", mismatches)
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
		fmt.Fprintf(in.stdout, "MISSING_UPSTREAM\t%s\t(curated ctx=%d max_out=%d)\n",
			in.id, in.cap.ContextWindow, in.cap.MaxOutputTokens)
		return 1
	}
	upCtx := intFromPtr(in.entry.MaxInputTokens)
	upOut := intFromPtr(in.entry.MaxOutputTokens)
	// Do not fall back to max_tokens: LiteLLM often uses it for output limits.
	if upCtx == 0 && upOut == 0 {
		fmt.Fprintf(in.stdout, "NO_LIMITS_UPSTREAM\t%s\n", in.id)
		return 1
	}
	return countLimitMismatches(in, upCtx, upOut)
}

func countLimitMismatches(in modelDiffInput, upCtx, upOut int) int {
	n := 0
	if upCtx != 0 && upCtx != in.cap.ContextWindow {
		fmt.Fprintf(in.stdout, "CONTEXT_MISMATCH\t%s\tcurated=%d\tlitellm=%d\n", in.id, in.cap.ContextWindow, upCtx)
		n++
	}
	if upOut != 0 && upOut != in.cap.MaxOutputTokens {
		fmt.Fprintf(in.stdout, "MAX_OUT_MISMATCH\t%s\tcurated=%d\tlitellm=%d\n", in.id, in.cap.MaxOutputTokens, upOut)
		n++
	}
	return n
}

func loadLiteLLM(file string, fetch bool) ([]byte, error) {
	switch {
	case strings.TrimSpace(file) != "":
		return os.ReadFile(file)
	case fetch:
		client := &http.Client{Timeout: 30 * time.Second}
		resp, err := client.Get(defaultLiteLLMURL)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("fetch %s: status %d", defaultLiteLLMURL, resp.StatusCode)
		}
		return io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	default:
		return nil, fmt.Errorf("provide -file PATH or -fetch")
	}
}

func intFromPtr(v *float64) int {
	if v == nil {
		return 0
	}
	return int(*v)
}
