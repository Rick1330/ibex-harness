package auth

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/Rick1330/ibex-harness/packages/logger"
)

type stubValidator struct {
	calls int
	res   *ValidateResult
	err   error
}

func (s *stubValidator) Validate(context.Context, string) (*ValidateResult, error) {
	s.calls++
	if s.err != nil {
		return nil, s.err
	}
	out := *s.res
	return &out, nil
}

func TestWrapWithCache_FromCacheOnSecondCall(t *testing.T) {
	inner := &stubValidator{res: &ValidateResult{
		OrgID: "org-a", Permissions: 3, ExpiresAt: time.Now().Add(time.Hour),
	}}
	wrapped, err := WrapWithCache(inner, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err != nil {
		t.Fatalf("WrapWithCache: %v", err)
	}
	r1, err := wrapped.Validate(context.Background(), "tok")
	if err != nil {
		t.Fatalf("first: %v", err)
	}
	if r1.FromCache {
		t.Fatal("first should not be cached")
	}
	r2, err := wrapped.Validate(context.Background(), "tok")
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if !r2.FromCache {
		t.Fatal("second should be FromCache")
	}
	if inner.calls != 1 {
		t.Fatalf("inner calls=%d want 1", inner.calls)
	}
}

func TestWrapWithCache_Invalidate(t *testing.T) {
	inner := &stubValidator{res: &ValidateResult{OrgID: "org-a"}}
	wrapped, err := WrapWithCache(inner, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err != nil {
		t.Fatalf("WrapWithCache: %v", err)
	}
	if _, err := wrapped.Validate(context.Background(), "tok"); err != nil {
		t.Fatalf("first: %v", err)
	}
	inv, ok := wrapped.(CacheInvalidator)
	if !ok {
		t.Fatal("wrapped validator must implement CacheInvalidator")
	}
	inv.Invalidate(authcache.TokenHash("tok"))
	if _, err := wrapped.Validate(context.Background(), "tok"); err != nil {
		t.Fatalf("after invalidate: %v", err)
	}
	if inner.calls != 2 {
		t.Fatalf("inner calls=%d want 2", inner.calls)
	}
}
