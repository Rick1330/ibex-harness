package providercap

import (
	"errors"
	"os"
	"strings"
	"testing"
	"time"
)

const validManifest = `{"version":"provider-capability-manifest.v1","generated_at":"2026-10-16T00:00:00Z","expires_at":"2099-01-01T00:00:00Z","models":[{"provider":"openai","model":"gpt-4o","context_window":128000,"max_output_tokens":16384,"tokenizer_family":"o200k_base","endpoint":"/v1/responses","capabilities":{"responses":{"state":"supported","provenance":{"source_url":"https://developers.openai.com/api/reference/resources/responses/methods/create","title":"Create","accessed_at":"2026-10-16T00:00:00Z"}},"reasoning":{"state":"unverified"}}}]}`

func TestLoadFailClosed(t *testing.T) {
	now := time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name, body string
		want       error
	}{
		{"wrong version", strings.Replace(validManifest, "provider-capability-manifest.v1", "other.v1", 1), ErrInvalidManifest},
		{"unknown field", strings.Replace(validManifest, "\"models\":", "\"extra\":true,\"models\":", 1), ErrInvalidManifest},
		{"stale", strings.Replace(validManifest, "2099-01-01T00:00:00Z", "2026-10-16T11:00:00Z", 1), ErrStaleManifest},
		{"supported without provenance", strings.Replace(validManifest, `{"state":"supported","provenance":{"source_url":"https://developers.openai.com/api/reference/resources/responses/methods/create","title":"Create","accessed_at":"2026-10-16T00:00:00Z"}}`, `{"state":"supported"}`, 1), ErrInvalidManifest},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := Load(strings.NewReader(tc.body), now)
			if !errors.Is(err, tc.want) {
				t.Fatalf("err=%v want %v", err, tc.want)
			}
		})
	}
}

func TestRequireDeniesUnverifiedAndUnsupported(t *testing.T) {
	s, err := Load(strings.NewReader(validManifest), time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Require("openai", "gpt-4o", "reasoning"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("got %v", err)
	}
	if err := s.Require("openai", "gpt-4o", "missing"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("got %v", err)
	}
	if err := s.Require("openai", "not-a-model", "responses"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("got %v", err)
	}
}

func TestSnapshotReadersAreDeepCopies(t *testing.T) {
	s, err := Load(strings.NewReader(validManifest), time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	m, ok := s.Lookup("openai", "gpt-4o")
	if !ok {
		t.Fatal("model missing")
	}
	m.Capabilities["responses"] = Claim{State: StateUnsupported}
	if err := s.Require("openai", "gpt-4o", "responses"); err != nil {
		t.Fatalf("mutating lookup changed snapshot: %v", err)
	}
	manifest := s.Manifest()
	manifest.Models[0].Capabilities["responses"] = Claim{State: StateUnsupported}
	if err := s.Require("openai", "gpt-4o", "responses"); err != nil {
		t.Fatalf("mutating manifest changed snapshot: %v", err)
	}
}

func TestLoadDefaultConfiguredPathDoesNotFallback(t *testing.T) {
	t.Setenv("IBEX_PROVIDER_CAPABILITY_MANIFEST", t.TempDir()+"/missing.json")
	if _, err := LoadDefault(time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)); err == nil {
		t.Fatal("configured missing manifest must fail")
	}
}

func TestLoadAllowStaleLoadsButRequireDenies(t *testing.T) {
	stale := strings.Replace(validManifest, "2099-01-01T00:00:00Z", "2026-10-16T11:00:00Z", 1)
	s, err := LoadAllowStale(strings.NewReader(stale), time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Require("openai", "gpt-4o", "responses"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("got %v", err)
	}
}

func TestLoadDefaultConfiguredValidPath(t *testing.T) {
	f := t.TempDir() + "/manifest.json"
	if err := os.WriteFile(f, []byte(validManifest), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("IBEX_PROVIDER_CAPABILITY_MANIFEST", f)
	if _, err := LoadDefault(time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)); err != nil {
		t.Fatal(err)
	}
}

func TestStaleLoaderVariants(t *testing.T) {
	stale := []byte(strings.Replace(validManifest, "2099-01-01T00:00:00Z", "2026-10-16T11:00:00Z", 1))
	now := time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)
	if _, err := LoadBytes(stale, now); !errors.Is(err, ErrStaleManifest) {
		t.Fatalf("LoadBytes err=%v", err)
	}
	f := t.TempDir() + "/stale.json"
	if err := os.WriteFile(f, stale, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadFileAllowStale(f, now); err != nil {
		t.Fatal(err)
	}
	t.Setenv("IBEX_PROVIDER_CAPABILITY_MANIFEST", f)
	if _, err := LoadDefaultAllowStale(now); err != nil {
		t.Fatal(err)
	}
}
