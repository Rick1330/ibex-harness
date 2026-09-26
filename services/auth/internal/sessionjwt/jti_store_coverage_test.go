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

func TestMemoryJTIStore_RevokeZeroTTLMarkers(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	if err := store.RevokeFamily(ctx, "fam0", 0); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSession(ctx, "sid0", 0); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeAccess(ctx, "jti0", 0); err != nil {
		t.Fatal(err)
	}
	if revoked, err := store.FamilyRevoked(ctx, "fam0"); err != nil || !revoked {
		t.Fatalf("family: %v %v", revoked, err)
	}
	if revoked, err := store.SessionRevoked(ctx, "sid0"); err != nil || !revoked {
		t.Fatalf("session: %v %v", revoked, err)
	}
	if revoked, err := store.AccessRevoked(ctx, "jti0"); err != nil || !revoked {
		t.Fatalf("access: %v %v", revoked, err)
	}
}

func redisStore(t *testing.T) (*sessionjwt.RedisJTIStore, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rdb.Close() })
	store, err := sessionjwt.NewRedisJTIStore(rdb)
	if err != nil {
		t.Fatal(err)
	}
	return store, mr
}

func TestRedisJTIStore_EmptyFamilyAndSessionOnlyRevoke(t *testing.T) {
	t.Parallel()
	store, _ := redisStore(t)
	ctx := context.Background()
	if revoked, err := store.FamilyRevoked(ctx, ""); err != nil || revoked {
		t.Fatalf("empty family: revoked=%v err=%v", revoked, err)
	}
	if err := store.RevokeFamily(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSession(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeAccess(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSessionAndFamily(ctx, "", "fam", time.Minute); err == nil {
		t.Fatal("expected empty session id error")
	}
	if err := store.RevokeSessionAndFamily(ctx, "sid-only", "", time.Minute); err != nil {
		t.Fatal(err)
	}
	sessionRevoked, err := store.SessionRevoked(ctx, "sid-only")
	if err != nil || !sessionRevoked {
		t.Fatalf("session-only: revoked=%v err=%v", sessionRevoked, err)
	}
}

func TestRedisJTIStore_ZeroTTLHappyPaths(t *testing.T) {
	t.Parallel()
	store, _ := redisStore(t)
	ctx := context.Background()
	ok, err := store.ConsumeOnce(ctx, "jti-z", 0)
	requireConsume(t, consumeResult{ok, err}, true, "consume zero")
	if err := store.RevokeFamily(ctx, "fam-z", 0); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSession(ctx, "sid-z", 0); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeAccess(ctx, "acc-z", 0); err != nil {
		t.Fatal(err)
	}
	first, err := store.ConsumeStepUp(ctx, "step-z", 0)
	requireConsume(t, consumeResult{first, err}, true, "step zero")
	if err := store.RevokeSessionAndFamily(ctx, "sid-ms", "fam-ms", 500*time.Microsecond); err != nil {
		t.Fatal(err)
	}
}

func TestRedisJTIStore_ErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	ctx := context.Background()
	mr.Close()
	cases := []struct {
		name string
		fn   func() error
	}{
		{"ConsumeOnce", func() error { _, err := store.ConsumeOnce(ctx, "j", time.Minute); return err }},
		{"RevokeFamily", func() error { return store.RevokeFamily(ctx, "f", time.Minute) }},
		{"FamilyRevoked", func() error { _, err := store.FamilyRevoked(ctx, "f"); return err }},
		{"RevokeSession", func() error { return store.RevokeSession(ctx, "s", time.Minute) }},
		{"RevokeSessionAndFamily", func() error {
			return store.RevokeSessionAndFamily(ctx, "s", "f", time.Minute)
		}},
		{"SessionRevoked", func() error { _, err := store.SessionRevoked(ctx, "s"); return err }},
		{"RevokeAccess", func() error { return store.RevokeAccess(ctx, "j", time.Minute) }},
		{"AccessRevoked", func() error { _, err := store.AccessRevoked(ctx, "j"); return err }},
		{"ConsumeStepUp", func() error { _, err := store.ConsumeStepUp(ctx, "s", time.Minute); return err }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if err := tc.fn(); err == nil {
				t.Fatal("expected redis error after close")
			}
		})
	}
}
