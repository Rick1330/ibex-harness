package modelpolicy

import (
	"path/filepath"
	"testing"
)

func TestMatch_ClaudeGlob(t *testing.T) {
	t.Parallel()
	cases := []struct {
		pattern, model string
		want           bool
	}{
		{"claude-*", "claude-sonnet-4-5", true},
		{"claude-*", "claude-", true},
		{"claude-*", "claude", false},
		{"claude-?", "claude-x", true},
		{"gpt-4o", "gpt-4o", true},
		{"gpt-4o", "gpt-4o-mini", false},
	}
	for _, tc := range cases {
		ok, err := Match(tc.pattern, tc.model)
		if err != nil {
			t.Fatalf("Match(%q,%q): %v", tc.pattern, tc.model, err)
		}
		if ok != tc.want {
			t.Fatalf("Match(%q,%q)=%v want %v", tc.pattern, tc.model, ok, tc.want)
		}
	}
}

func TestValidatePattern_Invalid(t *testing.T) {
	t.Parallel()
	if err := ValidatePattern(`claude-[`); err == nil {
		t.Fatal("expected invalid pattern error")
	}
	if _, err := filepath.Match(`claude-[`, "x"); err == nil {
		t.Fatal("sanity: filepath.Match should reject unbalanced [")
	}
	if err := ValidatePattern(""); err == nil {
		t.Fatal("expected empty pattern error")
	}
}

func TestEvaluatePolicies_PriorityFirstMatch(t *testing.T) {
	t.Parallel()
	policies := []Policy{
		{Pattern: "claude-*", Allowed: true, Priority: 10},
		{Pattern: "claude-sonnet-4-5", Allowed: false, Priority: 1},
	}
	dec, err := EvaluatePolicies(policies, "claude-sonnet-4-5")
	if err != nil {
		t.Fatal(err)
	}
	if !dec.Matched || dec.Allowed {
		t.Fatalf("want deny match, got %+v", dec)
	}
}

func TestEvaluatePolicies_NoMatchAllows(t *testing.T) {
	t.Parallel()
	dec, err := EvaluatePolicies([]Policy{{Pattern: "gpt-*", Allowed: false, Priority: 1}}, "claude-sonnet-4-5")
	if err != nil {
		t.Fatal(err)
	}
	if dec.Matched || !dec.Allowed {
		t.Fatalf("want platform allow, got %+v", dec)
	}
}

func TestResolveCandidateModel(t *testing.T) {
	t.Parallel()
	if got := ResolveCandidateModel("  gpt-4o  ", AgentDefaults{DefaultModel: "claude"}); got != "gpt-4o" {
		t.Fatalf("got %q", got)
	}
	if got := ResolveCandidateModel("", AgentDefaults{DefaultModel: "claude-sonnet-4-5"}); got != "claude-sonnet-4-5" {
		t.Fatalf("got %q", got)
	}
	if got := ResolveCandidateModel("  ", AgentDefaults{}); got != "" {
		t.Fatalf("got %q", got)
	}
}
