// Command diff_capabilities compares the curated BuiltInCapabilityCatalog against
// a LiteLLM model_prices_and_context_window.json snapshot (or live URL).
//
// Maintainer tooling only — not imported by the proxy binary and not a CI gate.
//
// Usage:
//
//	go run ./packages/provider/scripts/diff_capabilities \
//	  -file /path/to/model_prices_and_context_window.json
//
//	go run ./packages/provider/scripts/diff_capabilities -fetch
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const defaultLiteLLMURL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

type liteLLMEntry struct {
	MaxInputTokens  *float64 `json:"max_input_tokens"`
	MaxOutputTokens *float64 `json:"max_output_tokens"`
	MaxTokens       *float64 `json:"max_tokens"`
}

func main() {
	file := flag.String("file", "", "path to LiteLLM JSON snapshot")
	fetch := flag.Bool("fetch", false, "fetch LiteLLM JSON from GitHub")
	flag.Parse()

	raw, err := loadLiteLLM(*file, *fetch)
	if err != nil {
		fmt.Fprintf(os.Stderr, "diff_capabilities: %v\n", err)
		os.Exit(2)
	}

	var table map[string]liteLLMEntry
	if err := json.Unmarshal(raw, &table); err != nil {
		fmt.Fprintf(os.Stderr, "diff_capabilities: parse JSON: %v\n", err)
		os.Exit(2)
	}

	catalog := provider.BuiltInCapabilityCatalog()
	ids := make([]string, 0, len(catalog))
	for id := range catalog {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	mismatches := 0
	for _, id := range ids {
		cap := catalog[id]
		entry, ok := table[id]
		if !ok {
			fmt.Printf("MISSING_UPSTREAM\t%s\t(curated ctx=%d max_out=%d)\n", id, cap.ContextWindow, cap.MaxOutputTokens)
			mismatches++
			continue
		}
		upCtx := intFromPtr(entry.MaxInputTokens)
		if upCtx == 0 {
			upCtx = intFromPtr(entry.MaxTokens)
		}
		upOut := intFromPtr(entry.MaxOutputTokens)
		if upCtx != 0 && upCtx != cap.ContextWindow {
			fmt.Printf("CONTEXT_MISMATCH\t%s\tcurated=%d\tlitellm=%d\n", id, cap.ContextWindow, upCtx)
			mismatches++
		}
		if upOut != 0 && upOut != cap.MaxOutputTokens {
			fmt.Printf("MAX_OUT_MISMATCH\t%s\tcurated=%d\tlitellm=%d\n", id, cap.MaxOutputTokens, upOut)
			mismatches++
		}
		if upCtx == 0 && upOut == 0 {
			fmt.Printf("NO_LIMITS_UPSTREAM\t%s\n", id)
		}
	}

	if mismatches == 0 {
		fmt.Println("OK: curated models match LiteLLM context/max_output where present")
		return
	}
	fmt.Fprintf(os.Stderr, "diff_capabilities: %d mismatch(es)\n", mismatches)
	os.Exit(1)
}

func loadLiteLLM(file string, fetch bool) ([]byte, error) {
	switch {
	case file != "":
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
