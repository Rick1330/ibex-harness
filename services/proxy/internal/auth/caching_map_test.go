package auth

import (
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/authcache"
)

func TestUnit_MapAuthcacheErrors(t *testing.T) {
	t.Parallel()
	if !errors.Is(mapToAuthcacheErr(ErrInvalidToken), authcache.ErrInvalidToken) {
		t.Fatal("to invalid")
	}
	if !errors.Is(mapToAuthcacheErr(ErrAuthUnavailable), authcache.ErrUnavailable) {
		t.Fatal("to unavailable")
	}
	if !errors.Is(mapFromAuthcacheErr(authcache.ErrInvalidToken), ErrInvalidToken) {
		t.Fatal("from invalid")
	}
	if !errors.Is(mapFromAuthcacheErr(authcache.ErrUnavailable), ErrAuthUnavailable) {
		t.Fatal("from unavailable")
	}
	passthrough := errors.New("x")
	if mapToAuthcacheErr(passthrough) != passthrough {
		t.Fatal("to passthrough")
	}
	if mapFromAuthcacheErr(passthrough) != passthrough {
		t.Fatal("from passthrough")
	}
}

func TestUnit_ResultConverters(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	proxy := &ValidateResult{
		OrgID: "o", Permissions: 3, AgentID: "a", UserID: "u", TokenID: "t", ExpiresAt: now,
	}
	ac := proxyResultToAuthcache(proxy)
	back := authcacheResultToProxy(ac)
	if back.OrgID != "o" || back.TokenID != "t" || back.Permissions != 3 {
		t.Fatalf("roundtrip=%+v", back)
	}
	ac.FromCache = true
	if !authcacheResultToProxy(ac).FromCache {
		t.Fatal("FromCache lost")
	}
}
