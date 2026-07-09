package gobench

import (
	"strings"
	"testing"
)

func TestStageAuthProducesStablePrefix(t *testing.T) {
	got := stageAuth()
	if len(got) != 16 {
		t.Fatalf("stageAuth() len = %d, want 16 hex chars", len(got))
	}
	if got != stageAuth() {
		t.Fatal("stageAuth() not stable across calls")
	}
}

func TestStageRateLimitScalesWithKeyMaterial(t *testing.T) {
	short := stageRateLimit("ab")
	long := stageRateLimit(strings.Repeat("x", 32))
	if long <= short {
		t.Fatalf("rate limit score short=%d long=%d", short, long)
	}
}

func TestStageDirectiveResolveNonEmpty(t *testing.T) {
	if got := stageDirectiveResolve(3); got == "" {
		t.Fatal("expected directive payload")
	}
}

func TestStagePromptInjectWrapsInput(t *testing.T) {
	const input = "directive:test"
	got := stagePromptInject(input)
	if !strings.HasPrefix(got, "[system]") || !strings.HasSuffix(got, "[/system]") {
		t.Fatalf("unexpected prompt inject wrapper: %q", got)
	}
}

func TestBenchmarkProxyOverheadAllocates(t *testing.T) {
	allocs := testing.AllocsPerRun(1, func() {
		token := stageAuth()
		limit := stageRateLimit(token)
		dir := stageDirectiveResolve(limit)
		_ = stagePromptInject(dir)
	})
	if allocs == 0 {
		t.Fatal("expected proxy overhead path to allocate")
	}
}
