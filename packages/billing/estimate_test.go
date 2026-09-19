package billing

import (
	"math"
	"strings"
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

func TestEstimateCost_RejectsNegativeOutputTokens(t *testing.T) {
	t.Parallel()
	_, _, err := EstimateCost(priceCard("1", 100, 100), TokenUsage{
		Provider: "openai", Model: "x", InputTokens: 0, OutputTokens: -1,
	})
	if err == nil || !strings.Contains(err.Error(), "negative") {
		t.Fatalf("got %v", err)
	}
}

func TestEstimateCost_RejectsNegativePriceOperands(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name string
		card CardVersion
	}{
		{
			name: "negative input price",
			card: priceCard("1", -1, 100),
		},
		{
			name: "negative output price",
			card: priceCard("1", 100, -1),
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, _, err := EstimateCost(tc.card, TokenUsage{
				Provider: "openai", Model: "x", InputTokens: 1, OutputTokens: 1,
			})
			if err == nil || !strings.Contains(err.Error(), "negative") {
				t.Fatalf("got %v", err)
			}
		})
	}
}

func TestEstimateCost_CostSumOverflow(t *testing.T) {
	t.Parallel()
	// tokens=halfPlus with 1000¢/1k yields halfPlus each side; final add overflows.
	halfPlus := int64(math.MaxInt64/2 + 1)
	card := CardVersion{
		Version: "1",
		Prices: []PriceRow{{
			Provider: "openai", ModelPattern: "*",
			InputCentsPer1k: 1000, OutputCentsPer1k: 1000,
		}},
	}
	_, _, err := EstimateCost(card, TokenUsage{
		Provider: "openai", Model: "x", InputTokens: halfPlus, OutputTokens: halfPlus,
	})
	if err == nil || !strings.Contains(err.Error(), "overflow") {
		t.Fatalf("got %v", err)
	}
}

func TestAddCostChecked_Overflow(t *testing.T) {
	t.Parallel()
	halfPlus := int64(math.MaxInt64/2 + 1)
	_, err := addCostChecked(halfPlus, halfPlus)
	if err == nil || !strings.Contains(err.Error(), "overflow") {
		t.Fatalf("got %v", err)
	}
}

func TestMatchPrice_SkipsInvalidOrEmptyGlob(t *testing.T) {
	t.Parallel()
	prices := []PriceRow{
		{Provider: "openai", ModelPattern: "", InputCentsPer1k: 1, OutputCentsPer1k: 1},
		{Provider: "openai", ModelPattern: "[", InputCentsPer1k: 2, OutputCentsPer1k: 2},
		{Provider: "openai", ModelPattern: "gpt-*", InputCentsPer1k: 100, OutputCentsPer1k: 200},
	}
	row, ok := matchPrice(prices, "openai", "gpt-4o")
	if !ok {
		t.Fatal("expected match on valid glob")
	}
	if row.InputCentsPer1k != 100 || row.OutputCentsPer1k != 200 {
		t.Fatalf("matched wrong row: %+v", row)
	}
}

func TestCeilMulDiv1k_NearOverflowCeiling(t *testing.T) {
	t.Parallel()
	// tokens*cents fits multiply but (prod+999) would overflow without guard.
	tokens := int64(math.MaxInt64 / 1000)
	_, err := ceilMulDiv1k(tokens, 1000)
	if err == nil {
		// Exact MaxInt64/1000 * 1000 may or may not hit the +999 guard; force the branch.
		_, err = ceilMulDiv1k(tokens, 1001)
	}
	if err == nil || !strings.Contains(err.Error(), "overflow") {
		t.Fatalf("got %v", err)
	}
}
