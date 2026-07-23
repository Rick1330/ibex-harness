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
	assertNotFromCache(t, wrapped, "tok")
	assertFromCache(t, wrapped, "tok")
	if inner.calls != 1 {
		t.Fatalf("inner calls=%d want 1", inner.calls)
	}
}

func assertNotFromCache(t *testing.T, v TokenValidator, token string) {
	t.Helper()
	res, err := v.Validate(context.Background(), token)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if res.FromCache {
		t.Fatal("expected miss")
	}
}

func assertFromCache(t *testing.T, v TokenValidator, token string) {
	t.Helper()
	res, err := v.Validate(context.Background(), token)
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if !res.FromCache {
		t.Fatal("expected hit")
	}
}

func TestUnit_WrapWithCacheInvalidate(t *testing.T) {
	t.Parallel()
	inner := &stubValidator{res: &ValidateResult{OrgID: "org-a"}}
	wrapped := mustWrap(t, inner)
	assertNotFromCache(t, wrapped, "tok")
	inv, ok := wrapped.(CacheInvalidator)
	if !ok {
		t.Fatal("expected CacheInvalidator")
	}
	inv.Invalidate(authcache.TokenHash("tok"))
	assertNotFromCache(t, wrapped, "tok")
	if inner.calls != 2 {
		t.Fatalf("inner calls=%d want 2", inner.calls)
	}
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
	if got == nil || got.Error() == "boom" {
		t.Fatalf("got=%v want wrapped boom", got)
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

func TestUnit_MapToAuthcacheErr(t *testing.T) {
	t.Parallel()
	if !errors.Is(mapToAuthcacheErr(ErrInvalidToken), authcache.ErrInvalidToken) {
		t.Fatal("invalid")
	}
	if !errors.Is(mapToAuthcacheErr(ErrAuthUnavailable), authcache.ErrUnavailable) {
		t.Fatal("unavailable")
	}
	if mapToAuthcacheErr(errors.New("x")).Error() != "x" {
		t.Fatal("passthrough")
	}
}
