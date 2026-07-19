package gobench

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
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

func TestStageRateLimitAllowsUnderCap(t *testing.T) {
	limiter, cleanup := newTestRateLimiter(t)
	defer cleanup()
	res, err := limiter.Check(context.Background(), benchOrgID, uuid.Nil)
	if err != nil {
		t.Fatalf("Check: %v", err)
	}
	if !res.Allowed {
		t.Fatal("expected rate limit allow under high RPM cap")
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
	limiter, cleanup := newTestRateLimiter(t)
	defer cleanup()
	ctx := context.Background()

	allocs := testing.AllocsPerRun(1, func() {
		_ = stageAuth()
		if _, err := limiter.Check(ctx, benchOrgID, uuid.Nil); err != nil {
			t.Fatalf("rate limit check: %v", err)
		}
		dir := stageDirectiveResolve(1)
		_ = stagePromptInject(dir)
	})
	if allocs == 0 {
		t.Fatal("expected proxy overhead path to allocate")
	}
}
