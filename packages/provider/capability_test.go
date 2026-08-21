package provider

import (
	"errors"
	"sync"
	"testing"
)

func TestUnit_BuiltInCapabilityCatalog_CoversPhase25Models(t *testing.T) {
	t.Parallel()
	catalog := BuiltInCapabilityCatalog()
	want := []ModelCapability{
		{ModelID: "gpt-4o", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 16_384, SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyO200kBase},
		{ModelID: "gpt-4o-mini", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 16_384, SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyO200kBase},
		{ModelID: "gpt-4-turbo", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 4_096, SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyCL100kBase},
		{ModelID: "gpt-3.5-turbo", Provider: "openai", ContextWindow: 16_385, MaxOutputTokens: 4_096, SupportsTools: true, SupportsVision: false, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyCL100kBase},
		{ModelID: "claude-sonnet-4-5", Provider: "anthropic", ContextWindow: 200_000, MaxOutputTokens: 64_000, SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyClaude},
		{ModelID: "claude-haiku-4-5", Provider: "anthropic", ContextWindow: 200_000, MaxOutputTokens: 64_000, SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyClaude},
		{ModelID: "claude-opus-4-5", Provider: "anthropic", ContextWindow: 200_000, MaxOutputTokens: 64_000, SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyClaude},
	}
	if len(catalog) != len(want) {
		t.Fatalf("catalog size=%d want %d", len(catalog), len(want))
	}
	for _, tc := range want {
		got, ok := catalog.Lookup(tc.ModelID)
		if !ok {
			t.Fatalf("missing capability for %q", tc.ModelID)
		}
		if err := ValidateBuiltinCapability(got); err != nil {
			t.Fatalf("%s: %v", tc.ModelID, err)
		}
		if got != tc {
			t.Fatalf("%s: got %+v want %+v", tc.ModelID, got, tc)
		}
	}
}

func TestUnit_MergeCapabilityCatalog_OverlayWins(t *testing.T) {
	t.Parallel()
	base := CatalogFromCapabilities(ModelCapability{
		ModelID: "gpt-4o", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 16_384,
		SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyO200kBase,
	})
	overlay := CatalogFromCapabilities(ModelCapability{
		ModelID: "gpt-4o", Provider: "openai", ContextWindow: 64_000, MaxOutputTokens: 8_192,
		SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyO200kBase,
	})
	merged := MergeCapabilityCatalog(base, overlay)
	cap, ok := merged.Lookup("gpt-4o")
	if !ok {
		t.Fatal("missing gpt-4o")
	}
	if cap.ContextWindow != 64_000 || cap.MaxOutputTokens != 8_192 {
		t.Fatalf("overlay not applied: %+v", cap)
	}
}

func TestUnit_NewRegistry_MissingCapability(t *testing.T) {
	t.Parallel()
	_, err := NewRegistry(CapabilityCatalog{}, stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if !errors.Is(err, ErrMissingCapability) {
		t.Fatalf("err=%v want ErrMissingCapability", err)
	}
}

func TestUnit_NewRegistry_ModelIDMismatch(t *testing.T) {
	t.Parallel()
	catalog := CapabilityCatalog{
		"gpt-4o": {
			ModelID: "gpt-4o-mini", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 16_384,
			SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyO200kBase,
		},
	}
	_, err := NewRegistry(catalog, stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if !errors.Is(err, ErrInvalidCapability) {
		t.Fatalf("err=%v want ErrInvalidCapability", err)
	}
}

func TestUnit_NewRegistry_InvalidCapability(t *testing.T) {
	t.Parallel()
	catalog := CapabilityCatalog{
		"gpt-4o": {
			ModelID: "gpt-4o", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 16_384,
			SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: "not-a-family",
		},
	}
	_, err := NewRegistry(catalog, stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if !errors.Is(err, ErrInvalidCapability) {
		t.Fatalf("err=%v want ErrInvalidCapability", err)
	}
}

func TestUnit_Registry_CapabilityKnownAndUnknown(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(BuiltInCapabilityCatalog(), stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	cap, ok := reg.Capability("gpt-4o")
	if !ok {
		t.Fatal("expected capability")
	}
	if cap.ContextWindow != 128_000 {
		t.Fatalf("ContextWindow=%d", cap.ContextWindow)
	}
	if _, ok := reg.Capability("no-such-model"); ok {
		t.Fatal("expected miss")
	}
}

func TestUnit_Registry_NilCapability(t *testing.T) {
	t.Parallel()
	var reg *Registry
	if _, ok := reg.Capability("gpt-4o"); ok {
		t.Fatal("nil registry should miss")
	}
}

func TestUnit_Registry_ConcurrentCapability(t *testing.T) {
	t.Parallel()
	reg, err := NewRegistry(BuiltInCapabilityCatalog(), stubProvider{name: "openai", models: []string{"gpt-4o"}})
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	var wg sync.WaitGroup
	for range 32 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cap, ok := reg.Capability("gpt-4o")
			if !ok || cap.ModelID != "gpt-4o" {
				t.Errorf("Capability failed: ok=%v cap=%+v", ok, cap)
			}
		}()
	}
	wg.Wait()
}

func TestUnit_ValidateCapability(t *testing.T) {
	t.Parallel()
	valid := ModelCapability{
		ModelID: "gpt-4o", Provider: "openai", ContextWindow: 128_000, MaxOutputTokens: 16_384,
		SupportsTools: true, SupportsVision: true, SupportsStreaming: true, TokenizerFamily: TokenizerFamilyO200kBase,
	}
	cases := []struct {
		name string
		cap  ModelCapability
		fn   func(ModelCapability) error
		ok   bool
	}{
		{"valid overlay", valid, ValidateCapability, true},
		{"valid builtin", valid, ValidateBuiltinCapability, true},
		{"unknown tokenizer overlay ok", withFamily(valid, TokenizerFamilyUnknown), ValidateCapability, true},
		{"unknown tokenizer builtin reject", withFamily(valid, TokenizerFamilyUnknown), ValidateBuiltinCapability, false},
		{"bad tokenizer", withFamily(valid, "x"), ValidateCapability, false},
		{"empty id", ModelCapability{Provider: "openai", ContextWindow: 1, MaxOutputTokens: 1, TokenizerFamily: TokenizerFamilyO200kBase}, ValidateCapability, false},
		{"zero window", ModelCapability{ModelID: "m", Provider: "openai", MaxOutputTokens: 1, TokenizerFamily: TokenizerFamilyO200kBase}, ValidateCapability, false},
		{"max out exceeds ctx", ModelCapability{ModelID: "m", Provider: "openai", ContextWindow: 10, MaxOutputTokens: 11, TokenizerFamily: TokenizerFamilyO200kBase}, ValidateCapability, false},
		{"empty tokenizer", ModelCapability{ModelID: "m", Provider: "openai", ContextWindow: 1, MaxOutputTokens: 1}, ValidateCapability, false},
	}
	for _, tc := range cases {
		err := tc.fn(tc.cap)
		if tc.ok && err != nil {
			t.Fatalf("%s: unexpected err %v", tc.name, err)
		}
		if !tc.ok && err == nil {
			t.Fatalf("%s: expected error", tc.name)
		}
	}
}

func withFamily(cap ModelCapability, family string) ModelCapability {
	cap.TokenizerFamily = family
	return cap
}
