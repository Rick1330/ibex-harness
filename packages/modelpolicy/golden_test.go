package modelpolicy

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

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
	path := filepath.Join("testdata", "model_pattern_golden.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read golden: %v", err)
	}
	var g goldenFile
	if err := json.Unmarshal(raw, &g); err != nil {
		t.Fatalf("decode golden: %v", err)
	}
	return g
}

func TestValidatePattern_GoldenCorpus(t *testing.T) {
	t.Parallel()
	g := loadGolden(t)
	for _, pattern := range g.Accept {
		if err := ValidatePattern(pattern); err != nil {
			t.Fatalf("accept %q: %v", pattern, err)
		}
	}
	for _, pattern := range g.Reject {
		if err := ValidatePattern(pattern); err == nil {
			t.Fatalf("reject %q: expected error", pattern)
		}
	}
}

func TestMatch_SlashSemanticsGolden(t *testing.T) {
	t.Parallel()
	g := loadGolden(t)
	for _, tc := range g.SlashSemantics {
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
}
