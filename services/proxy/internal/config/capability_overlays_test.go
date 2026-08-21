package config

import (
	"fmt"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

func TestParseCapabilityOverlays_Empty(t *testing.T) {
	t.Parallel()
	got, err := ParseCapabilityOverlays("  ")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if got != nil {
		t.Fatalf("got=%v", got)
	}
}

func TestParseCapabilityOverlays_Valid(t *testing.T) {
	t.Parallel()
	raw := `[{
		"model_id":"openai/gpt-oss-20b:free",
		"provider":"openai",
		"context_window":8192,
		"max_output_tokens":2048,
		"supports_tools":false,
		"supports_vision":false,
		"supports_streaming":true,
		"tokenizer_family":"unknown"
	}]`
	got, err := ParseCapabilityOverlays(raw)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if len(got) != 1 || got[0].ModelID != "openai/gpt-oss-20b:free" {
		t.Fatalf("got=%+v", got)
	}
	if got[0].TokenizerFamily != provider.TokenizerFamilyUnknown {
		t.Fatalf("tokenizer=%q", got[0].TokenizerFamily)
	}
}

func TestParseCapabilityOverlays_RejectsInvalid(t *testing.T) {
	t.Parallel()
	cases := []string{
		`{`,
		`[{"model_id":"","provider":"openai","context_window":1,"max_output_tokens":1,"tokenizer_family":"x"}]`,
		`[{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"tokenizer_family":"x"},{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"tokenizer_family":"x"}]`,
	}
	for _, raw := range cases {
		if _, err := ParseCapabilityOverlays(raw); err == nil {
			t.Fatalf("expected error for %q", raw)
		}
	}
}

func TestParseCapabilityOverlays_RejectsOversized(t *testing.T) {
	t.Parallel()
	parts := make([]string, 0, maxCapabilityOverlayEntries+1)
	for i := 0; i < maxCapabilityOverlayEntries+1; i++ {
		parts = append(parts, fmt.Sprintf(
			`{"model_id":"extra-%d","provider":"openai","context_window":1,"max_output_tokens":1,"tokenizer_family":"x"}`, i,
		))
	}
	raw := "[" + strings.Join(parts, ",") + "]"
	_, err := ParseCapabilityOverlays(raw)
	if err == nil || !strings.Contains(err.Error(), "at most") {
		t.Fatalf("err=%v", err)
	}
}
