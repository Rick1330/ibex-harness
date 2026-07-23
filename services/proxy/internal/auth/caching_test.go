package auth

import (
	"context"
	"errors"
	"strings"
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
		AgentID: "agent-1", UserID: "user-1", TokenID: "tok-1",
	}}
	wrapped, err := WrapWithCache(inner, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err != nil {
		t.Fatalf("WrapWithCache: %v", err)
	}
	r1, err := wrapped.Validate(context.Background(), "tok")
	if err != nil || r1.FromCache {
		t.Fatalf("first: err=%v fromCache=%v", err, r1 != nil && r1.FromCache)
	}
	r2, err := wrapped.Validate(context.Background(), "tok")
	if err != nil || !r2.FromCache {
		t.Fatalf("second: err=%v fromCache=%v", err, r2 != nil && r2.FromCache)
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

func TestWrapWithCache_NilInner(t *testing.T) {
	_, err := WrapWithCache(nil, authcache.Config{}, logger.Discard("proxy"), authcache.NoopMetrics{})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestWrapWithCache_MapsInvalidAndUnavailable(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want error
	}{
		{name: "invalid", err: ErrInvalidToken, want: ErrInvalidToken},
		{name: "unavailable", err: ErrAuthUnavailable, want: ErrAuthUnavailable},
		{name: "other", err: errors.New("boom"), want: nil},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			inner := &stubValidator{err: tc.err}
			wrapped, err := WrapWithCache(inner, authcache.Config{}, logger.Discard("proxy"), nil)
			if err != nil {
				t.Fatalf("WrapWithCache: %v", err)
			}
			_, got := wrapped.Validate(context.Background(), "tok")
			if tc.name == "other" {
				if got == nil || !strings.Contains(got.Error(), "boom") {
					t.Fatalf("got=%v", got)
				}
				return
			}
			if !errors.Is(got, tc.want) {
				t.Fatalf("got=%v want %v", got, tc.want)
			}
		})
	}
}

func TestMapToAuthcacheErr(t *testing.T) {
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
