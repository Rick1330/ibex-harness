package auth

import (
	"context"
	"errors"
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

func mustWrap(t *testing.T, inner TokenValidator) TokenValidator {
	t.Helper()
	wrapped, err := WrapWithCache(inner, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err != nil {
		t.Fatalf("WrapWithCache: %v", err)
	}
	return wrapped
}

func TestUnit_WrapWithCacheFromCacheOnSecondCall(t *testing.T) {
	t.Parallel()
	inner := &stubValidator{res: &ValidateResult{
		OrgID: "org-a", Permissions: 3, ExpiresAt: time.Now().Add(time.Hour),
		AgentID: "agent-1", UserID: "user-1", TokenID: "tok-1",
	}}
	wrapped := mustWrap(t, inner)
	assertCacheHit(t, wrapped, "tok", false)
	assertCacheHit(t, wrapped, "tok", true)
	assertInnerCalls(t, inner, 1)
}

func assertCacheHit(t *testing.T, v TokenValidator, token string, wantHit bool) {
	t.Helper()
	res, err := v.Validate(context.Background(), token)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if res.FromCache != wantHit {
		t.Fatalf("FromCache=%v want %v", res.FromCache, wantHit)
	}
}

func assertInnerCalls(t *testing.T, inner *stubValidator, want int) {
	t.Helper()
	if inner.calls != want {
		t.Fatalf("inner calls=%d want %d", inner.calls, want)
	}
}

func TestUnit_WrapWithCacheInvalidate(t *testing.T) {
	t.Parallel()
	runInvalidateMiss(t, invalidateByHash)
}

func TestUnit_WrapWithCacheInvalidateByTokenID(t *testing.T) {
	t.Parallel()
	runInvalidateMiss(t, invalidateByTokenID)
}

type invalidateFn func(CacheInvalidator)

func invalidateByHash(inv CacheInvalidator) {
	inv.Invalidate(authcache.TokenHash("tok"))
}

func invalidateByTokenID(inv CacheInvalidator) {
	inv.InvalidateByTokenID("tok-uuid")
}

func runInvalidateMiss(t *testing.T, invalidate invalidateFn) {
	t.Helper()
	inner := &stubValidator{res: &ValidateResult{OrgID: "org-a", TokenID: "tok-uuid"}}
	wrapped := mustWrap(t, inner)
	assertCacheHit(t, wrapped, "tok", false)
	invalidate(mustInvalidator(t, wrapped))
	assertCacheHit(t, wrapped, "tok", false)
	assertInnerCalls(t, inner, 2)
}

func mustInvalidator(t *testing.T, v TokenValidator) CacheInvalidator {
	t.Helper()
	inv, ok := v.(CacheInvalidator)
	if !ok {
		t.Fatal("expected CacheInvalidator")
	}
	return inv
}

func TestUnit_WrapWithCacheNilInner(t *testing.T) {
	t.Parallel()
	_, err := WrapWithCache(nil, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_WrapWithCacheMapsInvalid(t *testing.T) {
	t.Parallel()
	assertMappedErr(t, ErrInvalidToken, ErrInvalidToken)
}

func TestUnit_WrapWithCacheMapsUnavailable(t *testing.T) {
	t.Parallel()
	assertMappedErr(t, ErrAuthUnavailable, ErrAuthUnavailable)
}

func TestUnit_WrapWithCacheMapsOther(t *testing.T) {
	t.Parallel()
	inner := &stubValidator{err: errors.New("boom")}
	wrapped := mustWrap(t, inner)
	_, got := wrapped.Validate(context.Background(), "tok")
	if got == nil {
		t.Fatal("expected error")
	}
	if got.Error() == "boom" {
		t.Fatal("want wrapped boom error")
	}
}

func assertMappedErr(t *testing.T, upstream, want error) {
	t.Helper()
	inner := &stubValidator{err: upstream}
	wrapped := mustWrap(t, inner)
	_, got := wrapped.Validate(context.Background(), "tok")
	if !errors.Is(got, want) {
		t.Fatalf("got=%v want %v", got, want)
	}
}
