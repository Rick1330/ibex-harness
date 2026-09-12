package modelpolicy

import (
	_ "embed" // registers embed.FS for go:embed golden JSON corpus in this package
	"encoding/json"
	"testing"
)

//go:embed testdata/model_pattern_golden.json
var goldenJSON []byte

type goldenFile struct {
	Accept         []string          `json:"accept"`
	Reject         []string          `json:"reject"`
	SlashSemantics []goldenSlashCase `json:"slash_semantics"`
}

type goldenSlashCase struct {
	Pattern string `json:"pattern"`
	Model   string `json:"model"`
	Match   bool   `json:"match"`
}

func loadGolden(t *testing.T) goldenFile {
	t.Helper()
	var g goldenFile
	if err := json.Unmarshal(goldenJSON, &g); err != nil {
		t.Fatalf("decode golden: %v", err)
	}
	return g
}

func TestValidatePattern_GoldenCorpus(t *testing.T) {
	t.Parallel()
	g := loadGolden(t)
	assertPatternsAccepted(t, g.Accept)
	assertPatternsRejected(t, g.Reject)
}

func assertPatternsAccepted(t *testing.T, patterns []string) {
	t.Helper()
	for _, pattern := range patterns {
		if err := ValidatePattern(pattern); err != nil {
			t.Fatalf("accept %q: %v", pattern, err)
		}
	}
}

func assertPatternsRejected(t *testing.T, patterns []string) {
	t.Helper()
	for _, pattern := range patterns {
		if err := ValidatePattern(pattern); err == nil {
			t.Fatalf("reject %q: expected error", pattern)
		}
	}
}

func TestMatch_SlashSemanticsGolden(t *testing.T) {
	t.Parallel()
	g := loadGolden(t)
	for _, tc := range g.SlashSemantics {
		assertSlashCase(t, tc)
	}
}

func assertSlashCase(t *testing.T, tc goldenSlashCase) {
	t.Helper()
	if err := ValidatePattern(tc.Pattern); err != nil {
		t.Fatalf("pattern %q: %v", tc.Pattern, err)
	}
	ok, err := Match(tc.Pattern, tc.Model)
	if err != nil {
		t.Fatalf("Match(%q,%q): %v", tc.Pattern, tc.Model, err)
	}
	if ok != tc.Match {
		t.Fatalf("Match(%q,%q)=%v want %v", tc.Pattern, tc.Model, ok, tc.Match)
	}
}
