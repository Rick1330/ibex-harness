package providercap

import (
	"errors"
	"strings"
	"testing"
	"time"
)

const validManifest = `{"version":"provider-capability-manifest.v1","generated_at":"2026-10-16T00:00:00Z","expires_at":"2026-11-10T00:00:00Z","models":[{"provider":"openai","model":"gpt-4o","context_window":128000,"max_output_tokens":16384,"tokenizer_family":"o200k_base","endpoint":"/v1/responses","capabilities":{"responses":{"state":"supported","provenance":{"source_url":"https://developers.openai.com/api/reference/resources/responses/methods/create","title":"Create","accessed_at":"2026-10-16T00:00:00Z"}},"reasoning":{"state":"unverified"}}}]}`

func TestLoadFailClosed(t *testing.T) {
	now := time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name, body string
		want       error
	}{
		{"wrong version", strings.Replace(validManifest, "provider-capability-manifest.v1", "other.v1", 1), ErrInvalidManifest},
		{"unknown field", strings.Replace(validManifest, "\"models\":", "\"extra\":true,\"models\":", 1), ErrInvalidManifest},
		{"stale", strings.Replace(validManifest, "2026-11-10T00:00:00Z", "2026-10-16T11:00:00Z", 1), ErrStaleManifest},
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
