package modelpolicy

import (
	"sync"
	"testing"
)

func TestFallbackChainForModel_AllowWithChain(t *testing.T) {
	t.Parallel()
	policies := []Policy{{
		Pattern: "gpt-*", Allowed: true, Priority: 10,
		FallbackChain: []string{"claude-sonnet-4-5", "local-m"},
	}}
	got, err := FallbackChainForModel(policies, "gpt-4o")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0] != "claude-sonnet-4-5" {
		t.Fatalf("got=%v", got)
	}
}

func TestFallbackChainForModel_EmptyOrDenyOrUnmatched(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name     string
		policies []Policy
		model    string
	}{
		{"empty_chain", []Policy{{Pattern: "gpt-*", Allowed: true, FallbackChain: []string{}}}, "gpt-4o"},
		{"deny", []Policy{{Pattern: "gpt-*", Allowed: false, FallbackChain: []string{"x"}}}, "gpt-4o"},
		{"unmatched", []Policy{{Pattern: "claude-*", Allowed: true, FallbackChain: []string{"x"}}}, "gpt-4o"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got, err := FallbackChainForModel(tc.policies, tc.model)
			if err != nil || got != nil {
				t.Fatalf("got=%v err=%v", got, err)
			}
		})
	}
}

func TestTruncateChain(t *testing.T) {
	t.Parallel()
	chain := []string{"a", "b", "c"}
	got := TruncateChain(chain, 1)
	if len(got) != 1 || got[0] != "a" {
		t.Fatalf("got=%v", got)
	}
	if TruncateChain(chain, 0)[0] != "a" {
		t.Fatal("maxDepth<1 clamps to 1")
	}
	if len(TruncateChain(chain, 10)) != 3 {
		t.Fatal("depth > len keeps all")
	}
}

func TestTruncateChain_Concurrent(t *testing.T) {
	t.Parallel()
	chain := []string{"a", "b", "c", "d"}
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func(depth int) {
			defer wg.Done()
			_ = TruncateChain(chain, depth%4)
		}(i)
	}
	wg.Wait()
}

func TestNormalizeFallbackChain(t *testing.T) {
	t.Parallel()
	if NormalizeFallbackChain([]string{"  ", ""}) != nil {
		t.Fatal("all empty")
	}
	got := NormalizeFallbackChain([]string{" a ", "", "b"})
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("got=%v", got)
	}
}
