package providercap

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func manifestWith(models string) string {
	return `{"version":"provider-capability-manifest.v1","generated_at":"2026-10-16T00:00:00Z","expires_at":"2026-11-10T00:00:00Z","models":` + models + `}`
}

func supportedModel(provider, model string) string {
	return `{"provider":"` + provider + `","model":"` + model + `","context_window":128000,"max_output_tokens":16384,"tokenizer_family":"o200k_base","endpoint":"/v1/responses","capabilities":{"responses":{"state":"supported","provenance":{"source_url":"https://example.test/responses","title":"Responses","accessed_at":"2026-10-16T00:00:00Z"}}}}`
}

func TestValidateRejectsMalformedManifests(t *testing.T) {
	now := time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)
	cases := []struct {
		name string
		body string
		want error
	}{
		{"trailing json", validManifest + `{"extra":true}`, ErrInvalidManifest},
		{"zero freshness window", strings.Replace(validManifest, `"generated_at":"2026-10-16T00:00:00Z"`, `"generated_at":"0001-01-01T00:00:00Z"`, 1), ErrInvalidManifest},
		{"expires before generated", strings.Replace(validManifest, `"expires_at":"2026-11-10T00:00:00Z"`, `"expires_at":"2026-10-01T00:00:00Z"`, 1), ErrInvalidManifest},
		{"generated in future", strings.Replace(validManifest, `"generated_at":"2026-10-16T00:00:00Z"`, `"generated_at":"2027-10-16T00:00:00Z"`, 1), ErrInvalidManifest},
		{"no models", manifestWith(`[]`), ErrInvalidManifest},
		{"model identity missing", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"model":"gpt-4o"`, `"model":"  "`, 1) + `]`), ErrInvalidManifest},
		{"duplicate model", manifestWith(`[` + supportedModel("openai", "gpt-4o") + `,` + supportedModel("openai", "gpt-4o") + `]`), ErrInvalidManifest},
		{"invalid limits", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"max_output_tokens":16384`, `"max_output_tokens":999999`, 1) + `]`), ErrInvalidManifest},
		{"nonpositive context", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"context_window":128000`, `"context_window":0`, 1) + `]`), ErrInvalidManifest},
		{"missing tokenizer", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"tokenizer_family":"o200k_base"`, `"tokenizer_family":""`, 1) + `]`), ErrInvalidManifest},
		{"invalid claim state", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"state":"supported"`, `"state":"maybe"`, 1) + `]`), ErrInvalidManifest},
		{"supported lacks source url", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"source_url":"https://example.test/responses"`, `"source_url":""`, 1) + `]`), ErrInvalidManifest},
		{"future provenance", manifestWith(`[` + strings.Replace(supportedModel("openai", "gpt-4o"), `"accessed_at":"2026-10-16T00:00:00Z"`, `"accessed_at":"2027-01-01T00:00:00Z"`, 1) + `]`), ErrInvalidManifest},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := Load(strings.NewReader(tc.body), now); !errors.Is(err, tc.want) {
				t.Fatalf("err=%v want %v", err, tc.want)
			}
		})
	}
}

func TestLoadWithZeroNowUsesCurrentTime(t *testing.T) {
	body := strings.Replace(validManifest, `"generated_at":"2026-10-16T00:00:00Z"`, `"generated_at":"2000-01-01T00:00:00Z"`, 1)
	body = strings.Replace(body, `"expires_at":"2026-11-10T00:00:00Z"`, `"expires_at":"2099-01-01T00:00:00Z"`, 1)
	if _, err := Load(strings.NewReader(body), time.Time{}); err != nil {
		t.Fatalf("zero-now load failed: %v", err)
	}
}

func TestLookupAndRequireNilAndMisses(t *testing.T) {
	var nilSnap *Snapshot
	if _, ok := nilSnap.Lookup("openai", "gpt-4o"); ok {
		t.Fatal("nil snapshot lookup must miss")
	}
	if err := nilSnap.Require("openai", "gpt-4o", "responses"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("nil snapshot require err=%v", err)
	}
	s, err := Load(strings.NewReader(validManifest), time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := s.Lookup("openai", "missing"); ok {
		t.Fatal("missing model must miss")
	}
	if err := s.Require("openai", "gpt-4o", "responses"); err != nil {
		t.Fatalf("supported claim require failed: %v", err)
	}
	if err := s.Require("other", "gpt-4o", "responses"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("unknown provider err=%v", err)
	}
}

func TestRequireRejectsExpiredSnapshot(t *testing.T) {
	body := strings.Replace(validManifest, `"generated_at":"2026-10-16T00:00:00Z"`, `"generated_at":"2019-01-01T00:00:00Z"`, 1)
	body = strings.Replace(body, `"expires_at":"2026-11-10T00:00:00Z"`, `"expires_at":"2020-01-01T00:00:00Z"`, 1)
	body = strings.Replace(body, `"accessed_at":"2026-10-16T00:00:00Z"`, `"accessed_at":"2019-01-01T00:00:00Z"`, 1)
	s, err := LoadAllowStale(strings.NewReader(body), time.Date(2019, 6, 1, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("allow-stale load failed: %v", err)
	}
	if err := s.Require("openai", "gpt-4o", "responses"); !errors.Is(err, ErrCapabilityUnknown) {
		t.Fatalf("expired snapshot must deny: %v", err)
	}
}

func TestLoadSeedManifestFromWorkingDirectory(t *testing.T) {
	dir := t.TempDir()
	seed := filepath.Join(dir, "infra", "provider-capabilities")
	if err := os.MkdirAll(seed, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(seed, "manifest.v1.json"), []byte(validManifest), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Chdir(dir)
	if _, err := LoadDefault(time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)); err != nil {
		t.Fatalf("seed load failed: %v", err)
	}
	if _, err := LoadDefaultAllowStale(time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)); err != nil {
		t.Fatalf("seed allow-stale load failed: %v", err)
	}
	if paths := seedManifestPaths(); len(paths) == 0 || !strings.HasSuffix(paths[0], "infra/provider-capabilities/manifest.v1.json") {
		t.Fatalf("seed paths=%v", paths)
	}
}

func TestLoadSeedManifestMissingFails(t *testing.T) {
	t.Chdir(t.TempDir())
	if _, err := LoadDefault(time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)); err == nil {
		t.Fatal("missing seed manifest must fail")
	}
}
