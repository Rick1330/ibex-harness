package billing

import (
	"testing"
)

func TestEstimateCost_FirstMatchWins(t *testing.T) {
	t.Parallel()
	card := CardVersion{
		Version: "2",
		Prices: []PriceRow{
			{Provider: "openai", ModelPattern: "gpt-4o*", InputCentsPer1k: 100, OutputCentsPer1k: 200},
			{Provider: "openai", ModelPattern: "*", InputCentsPer1k: 1, OutputCentsPer1k: 1},
		},
	}
	cents, ver, err := EstimateCost(card, TokenUsage{
		Provider: "openai", Model: "gpt-4o-mini", InputTokens: 1000, OutputTokens: 1000,
	})
	if err != nil {
		t.Fatal(err)
	}
	if ver != "2" {
		t.Fatalf("version=%s", ver)
	}
	// First row: 100+200 = 300 (exact 1k tokens)
	if cents != 300 {
		t.Fatalf("cents=%d want 300 (first match)", cents)
	}
}

func TestEstimateCost_CaseInsensitiveProvider(t *testing.T) {
	t.Parallel()
	card := CardVersion{
		Version: "1",
		Prices: []PriceRow{{
			Provider: "OpenAI", ModelPattern: "gpt-*",
			InputCentsPer1k: 1000, OutputCentsPer1k: 0,
		}},
	}
	cents, _, err := EstimateCost(card, TokenUsage{
		Provider: "openai", Model: "gpt-4", InputTokens: 1000, OutputTokens: 0,
	})
	if err != nil {
		t.Fatal(err)
	}
	if cents != 1000 {
		t.Fatalf("cents=%d", cents)
	}
}

func TestEstimateCost_EmptyVersion(t *testing.T) {
	t.Parallel()
	_, _, err := EstimateCost(CardVersion{
		Prices: []PriceRow{{Provider: "x", ModelPattern: "*", InputCentsPer1k: 1}},
	}, TokenUsage{Provider: "x", Model: "y", InputTokens: 1})
	if err == nil {
		t.Fatal("expected empty version error")
	}
}

func TestEstimateCost_ZeroTokens(t *testing.T) {
	t.Parallel()
	card := CardVersion{
		Version: "9",
		Prices: []PriceRow{{
			Provider: "anthropic", ModelPattern: "claude-*",
			InputCentsPer1k: 500, OutputCentsPer1k: 1500,
		}},
	}
	cents, ver, err := EstimateCost(card, TokenUsage{
		Provider: "anthropic", Model: "claude-3", InputTokens: 0, OutputTokens: 0,
	})
	if err != nil {
		t.Fatal(err)
	}
	if ver != "9" {
		t.Fatalf("version=%s", ver)
	}
	if cents != 0 {
		t.Fatalf("cents=%d want 0", cents)
	}
}
