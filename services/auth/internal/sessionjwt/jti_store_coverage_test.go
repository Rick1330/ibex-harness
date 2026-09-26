package sessionjwt_test

import (
	"context"
	"strconv"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestMemoryJTIStore_ZeroTTLEmptyIDsAndRevokeSessionAndFamily(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	ok, err := store.ConsumeOnce(ctx, "zero-ttl", 0)
	requireConsume(t, consumeResult{ok, err}, true, "zero ttl consume")
	if err := store.RevokeFamily(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSession(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeAccess(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSessionAndFamily(ctx, "sid", "fam", time.Minute); err != nil {
		t.Fatal(err)
	}
	sessionRevoked, err := store.SessionRevoked(ctx, "sid")
	if err != nil || !sessionRevoked {
		t.Fatalf("session: revoked=%v err=%v", sessionRevoked, err)
	}
	familyRevoked, err := store.FamilyRevoked(ctx, "fam")
	if err != nil || !familyRevoked {
		t.Fatalf("family: revoked=%v err=%v", familyRevoked, err)
	}
}

func TestMemoryJTIStore_RevocationMarkersExpire(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	if err := store.RevokeFamily(ctx, "fam-exp", 5*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSession(ctx, "sid-exp", 5*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeAccess(ctx, "jti-exp", 5*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	time.Sleep(15 * time.Millisecond)
	if revoked, err := store.FamilyRevoked(ctx, "fam-exp"); err != nil || revoked {
		t.Fatalf("family expired: revoked=%v err=%v", revoked, err)
	}
	if revoked, err := store.SessionRevoked(ctx, "sid-exp"); err != nil || revoked {
		t.Fatalf("session expired: revoked=%v err=%v", revoked, err)
	}
	if revoked, err := store.AccessRevoked(ctx, "jti-exp"); err != nil || revoked {
		t.Fatalf("access expired: revoked=%v err=%v", revoked, err)
	}
}

func TestMemoryJTIStore_MaybePurgeExpiredOn64thInsert(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	for i := 0; i < 64; i++ {
		ok, err := store.ConsumeOnce(ctx, "purge-"+strconv.Itoa(i), time.Millisecond)
		requireConsume(t, consumeResult{ok, err}, true, "seed")
	}
	time.Sleep(20 * time.Millisecond)
	ok, err := store.ConsumeOnce(ctx, "purge-trigger", time.Minute)
	requireConsume(t, consumeResult{ok, err}, true, "trigger purge")
	again, err := store.ConsumeOnce(ctx, "purge-0", time.Minute)
	requireConsume(t, consumeResult{again, err}, true, "purged key reusable")
}

func TestRedisJTIStore_EmptyFamilyAndErrors(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	store, err := sessionjwt.NewRedisJTIStore(rdb)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if revoked, err := store.FamilyRevoked(ctx, ""); err != nil || revoked {
		t.Fatalf("empty family: revoked=%v err=%v", revoked, err)
	}
	if err := store.RevokeSessionAndFamily(ctx, "sid-only", "", time.Minute); err != nil {
		t.Fatal(err)
	}
	sessionRevoked, err := store.SessionRevoked(ctx, "sid-only")
	if err != nil || !sessionRevoked {
		t.Fatalf("session-only: revoked=%v err=%v", sessionRevoked, err)
	}
	familyRevoked, err := store.FamilyRevoked(ctx, "missing-family")
	if err != nil || familyRevoked {
		t.Fatalf("missing family: revoked=%v err=%v", familyRevoked, err)
	}
	mr.Close()
	if _, err := store.ConsumeOnce(ctx, "after-close", time.Minute); err == nil {
		t.Fatal("expected redis error after close")
	}
	if err := store.RevokeFamily(ctx, "fam", time.Minute); err == nil {
		t.Fatal("expected revoke family error")
	}
	if _, err := store.FamilyRevoked(ctx, "fam"); err == nil {
		t.Fatal("expected family revoked error")
	}
	if err := store.RevokeSession(ctx, "sid", time.Minute); err == nil {
		t.Fatal("expected revoke session error")
	}
	if err := store.RevokeSessionAndFamily(ctx, "sid", "fam", time.Minute); err == nil {
		t.Fatal("expected revoke session+family error")
	}
	if _, err := store.SessionRevoked(ctx, "sid"); err == nil {
		t.Fatal("expected session revoked error")
	}
	if err := store.RevokeAccess(ctx, "jti", time.Minute); err == nil {
		t.Fatal("expected revoke access error")
	}
	if _, err := store.AccessRevoked(ctx, "jti"); err == nil {
		t.Fatal("expected access revoked error")
	}
	if _, err := store.ConsumeStepUp(ctx, "step", time.Minute); err == nil {
		t.Fatal("expected consume step-up error")
	}
}
