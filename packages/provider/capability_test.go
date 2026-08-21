package provider

import (
	"errors"
	"sync"
	"testing"
)

func TestUnit_BuiltInCapabilityCatalog_CoversPhase25Models(t *testing.T) {
	t.Parallel()
	catalog := BuiltInCapabilityCatalog()
	want := []struct {
		id, provider, tokenizer string
	}{
		{"gpt-4o", "openai", TokenizerFamilyO200kBase},
		{"gpt-4o-mini", "openai", TokenizerFamilyO200kBase},
		{"gpt-4-turbo", "openai", TokenizerFamilyCL100kBase},
		{"gpt-3.5-turbo", "openai", TokenizerFamilyCL100kBase},
		{"claude-sonnet-4-5", "anthropic", TokenizerFamilyClaude},
		{"claude-haiku-4-5", "anthropic", TokenizerFamilyClaude},
		{"claude-opus-4-5", "anthropic", TokenizerFamilyClaude},
	}
	for _, tc := range want {
		cap, ok := catalog.Lookup(tc.id)
		if !ok {
			t.Fatalf("missing capability for %q", tc.id)
		}
		if err := ValidateCapability(cap); err != nil {
			t.Fatalf("%s: %v", tc.id, err)
		}
		if cap.Provider != tc.provider {
			t.Fatalf("%s provider=%q want %q", tc.id, cap.Provider, tc.provider)
		}
		if cap.TokenizerFamily != tc.tokenizer {
			t.Fatalf("%s tokenizer=%q want %q", tc.id, cap.TokenizerFamily, tc.tokenizer)
		}
		if !cap.SupportsStreaming {
			t.Fatalf("%s: expected SupportsStreaming", tc.id)
		}
	}
}

func TestUnit_MergeCapabilityCatalog_OverlayWins(t *testing.T) {
	t.Parallel()
	base := CatalogFromCapabilities(openaiCap("gpt-4o", 128_000, 16_384, true, true, TokenizerFamilyO200kBase))
	overlay := CatalogFromCapabilities(ModelCapability{
		ModelID:           "gpt-4o",
		Provider:          "openai",
		ContextWindow:     64_000,
		MaxOutputTokens:   8_192,
		SupportsTools:     true,
		SupportsVision:    true,
		SupportsStreaming: true,
		TokenizerFamily:   TokenizerFamilyO200kBase,
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
	cases := []struct {
		name string
		cap  ModelCapability
		ok   bool
	}{
		{"valid", openaiCap("gpt-4o", 1, 1, true, true, TokenizerFamilyO200kBase), true},
		{"empty id", ModelCapability{Provider: "openai", ContextWindow: 1, MaxOutputTokens: 1, TokenizerFamily: "x"}, false},
		{"zero window", ModelCapability{ModelID: "m", Provider: "openai", MaxOutputTokens: 1, TokenizerFamily: "x"}, false},
		{"empty tokenizer", ModelCapability{ModelID: "m", Provider: "openai", ContextWindow: 1, MaxOutputTokens: 1}, false},
	}
	for _, tc := range cases {
		err := ValidateCapability(tc.cap)
		if tc.ok && err != nil {
			t.Fatalf("%s: unexpected err %v", tc.name, err)
		}
		if !tc.ok && err == nil {
			t.Fatalf("%s: expected error", tc.name)
		}
	}
}
