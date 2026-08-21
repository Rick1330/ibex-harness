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
	if got[0].SupportsStreaming != true || got[0].SupportsTools {
		t.Fatalf("flags=%+v", got[0])
	}
}

func TestParseCapabilityOverlays_RejectsInvalid(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		raw  string
		want string
	}{
		{"bad json", `{`, "invalid JSON"},
		{"null array", `null`, "expected a JSON array"},
		{"unknown field", `[{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"supports_tools":true,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown","extra":1}]`, "invalid JSON"},
		{"omitted supports_tools", `[{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown"}]`, "supports_tools is required"},
		{"empty model id", `[{"model_id":"","provider":"openai","context_window":1,"max_output_tokens":1,"supports_tools":true,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown"}]`, "empty ModelID"},
		{"bad tokenizer", `[{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"supports_tools":true,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"x"}]`, "unsupported TokenizerFamily"},
		{"max exceeds ctx", `[{"model_id":"a","provider":"openai","context_window":10,"max_output_tokens":11,"supports_tools":true,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown"}]`, "exceeds ContextWindow"},
		{"duplicate", `[{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"supports_tools":true,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown"},{"model_id":"a","provider":"openai","context_window":1,"max_output_tokens":1,"supports_tools":true,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown"}]`, "duplicate"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := ParseCapabilityOverlays(tc.raw)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err=%v want substring %q", err, tc.want)
			}
		})
	}
}

func TestParseCapabilityOverlays_RejectsOversized(t *testing.T) {
	t.Parallel()
	parts := make([]string, 0, maxCapabilityOverlayEntries+1)
	for i := 0; i < maxCapabilityOverlayEntries+1; i++ {
		parts = append(parts, fmt.Sprintf(
			`{"model_id":"extra-%d","provider":"openai","context_window":1,"max_output_tokens":1,"supports_tools":false,"supports_vision":false,"supports_streaming":true,"tokenizer_family":"unknown"}`, i,
		))
	}
	raw := "[" + strings.Join(parts, ",") + "]"
	_, err := ParseCapabilityOverlays(raw)
	if err == nil || !strings.Contains(err.Error(), "at most") {
		t.Fatalf("err=%v", err)
	}
}

func TestParseCapabilityOverlays_ByteLimit(t *testing.T) {
	t.Parallel()
	raw := strings.Repeat("a", maxCapabilityOverlayJSONBytes+1)
	_, err := ParseCapabilityOverlays(raw)
	if err == nil || !strings.Contains(err.Error(), "exceeds") {
		t.Fatalf("err=%v", err)
	}
}
