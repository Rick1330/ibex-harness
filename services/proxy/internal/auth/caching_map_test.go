package auth

import (
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/authcache"
	"github.com/google/uuid"
)

func TestUnit_MapAuthcacheErrors(t *testing.T) {
	t.Parallel()
	assertMappedTo(t, ErrInvalidToken, authcache.ErrInvalidToken)
	assertMappedTo(t, ErrAuthUnavailable, authcache.ErrUnavailable)
	assertMappedFrom(t, authcache.ErrInvalidToken, ErrInvalidToken)
	assertMappedFrom(t, authcache.ErrUnavailable, ErrAuthUnavailable)
	assertPassthrough(t, errors.New("x"))
}

func assertMappedTo(t *testing.T, in, want error) {
	t.Helper()
	if !errors.Is(mapToAuthcacheErr(in), want) {
		t.Fatalf("mapTo got=%v want %v", mapToAuthcacheErr(in), want)
	}
}

func assertMappedFrom(t *testing.T, in, want error) {
	t.Helper()
	if !errors.Is(mapFromAuthcacheErr(in), want) {
		t.Fatalf("mapFrom got=%v want %v", mapFromAuthcacheErr(in), want)
	}
}

func assertPassthrough(t *testing.T, err error) {
	t.Helper()
	if mapToAuthcacheErr(err) != err {
		t.Fatal("to passthrough")
	}
	if mapFromAuthcacheErr(err) != err {
		t.Fatal("from passthrough")
	}
}

func TestUnit_ResultConverters(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	proxy := &ValidateResult{
		OrgID:       uuid.MustParse("11111111-1111-4111-8111-111111111111"),
		Permissions: 3,
		AgentID:     uuid.MustParse("22222222-2222-4222-8222-222222222222"),
		UserID:      "u",
		TokenID:     "t",
		ExpiresAt:   now,
	}
	ac := proxyResultToAuthcache(proxy)
	back := authcacheResultToProxy(ac)
	assertResultField(t, "org_id", back.OrgID.String(), "11111111-1111-4111-8111-111111111111")
	assertResultField(t, "token_id", back.TokenID, "t")
	assertResultPerms(t, back.Permissions, 3)
	assertFromCacheRoundTrip(t, ac)
}

func assertResultField(t *testing.T, name, got, want string) {
	t.Helper()
	if got != want {
		t.Fatalf("%s=%q want %q", name, got, want)
	}
}

func assertResultPerms(t *testing.T, got, want int64) {
	t.Helper()
	if got != want {
		t.Fatalf("permissions=%d want %d", got, want)
	}
}

func assertFromCacheRoundTrip(t *testing.T, ac *authcache.Result) {
	t.Helper()
	ac.FromCache = true
	if !authcacheResultToProxy(ac).FromCache {
		t.Fatal("FromCache lost")
	}
}
