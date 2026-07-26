package gobench

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestStageAuthLRUHit(t *testing.T) {
	s := newWarmStages(t)
	res, err := s.auth.Validate(context.Background(), s.token)
	if err != nil {
		t.Fatalf("warm Validate: %v", err)
	}
	res, err = s.auth.Validate(context.Background(), s.token)
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if !res.FromCache {
		t.Fatal("expected authcache LRU hit")
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

func TestStageDirectiveResolveHasContent(t *testing.T) {
	s := newWarmStages(t)
	got, err := s.resolver.Resolve(context.Background(), s.orgID, s.agentID)
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if !got.HasContent() {
		t.Fatal("expected directive content on warm Redis hit")
	}
}

func TestStagePromptInjectAddsSystem(t *testing.T) {
	s := newWarmStages(t)
	got := stagePromptInject(s)
	if len(got) < 2 {
		t.Fatalf("len=%d", len(got))
	}
	if got[0].Role != "system" || got[0].Content != s.directive {
		t.Fatalf("first message=%+v", got[0])
	}
}

func TestBenchmarkProxyOverheadAllocates(t *testing.T) {
	s := newWarmStages(t)
	allocs := testing.AllocsPerRun(1, func() {
		if _, err := s.auth.Validate(context.Background(), s.token); err != nil {
			t.Fatalf("auth: %v", err)
		}
		if _, err := s.limiter.Check(context.Background(), s.orgID, uuid.Nil); err != nil {
			t.Fatalf("rl: %v", err)
		}
		if _, err := s.resolver.Resolve(context.Background(), s.orgID, s.agentID); err != nil {
			t.Fatalf("directive: %v", err)
		}
		_ = stagePromptInject(s)
	})
	if allocs == 0 {
		t.Fatal("expected proxy overhead path to allocate")
	}
}
