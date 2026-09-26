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

func TestMemoryJTIStore_ZeroTTLConsume(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ok, err := store.ConsumeOnce(context.Background(), "zero-ttl", 0)
	requireConsume(t, consumeResult{ok, err}, true, "zero ttl consume")
}

func TestMemoryJTIStore_EmptyIDRevokesAreNoOps(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	if err := store.RevokeFamily(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeSession(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := store.RevokeAccess(ctx, "", time.Minute); err != nil {
		t.Fatal(err)
	}
}

func TestMemoryJTIStore_RevokeSessionAndFamilySuccess(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
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

func TestMemoryJTIStore_FamilyRevocationMarkerExpires(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	if err := store.RevokeFamily(ctx, "fam-exp", 5*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	time.Sleep(15 * time.Millisecond)
	if revoked, err := store.FamilyRevoked(ctx, "fam-exp"); err != nil || revoked {
		t.Fatalf("family expired: revoked=%v err=%v", revoked, err)
	}
}

func TestMemoryJTIStore_SessionRevocationMarkerExpires(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	if err := store.RevokeSession(ctx, "sid-exp", 5*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	time.Sleep(15 * time.Millisecond)
	if revoked, err := store.SessionRevoked(ctx, "sid-exp"); err != nil || revoked {
		t.Fatalf("session expired: revoked=%v err=%v", revoked, err)
	}
}

func TestMemoryJTIStore_AccessRevocationMarkerExpires(t *testing.T) {
	t.Parallel()
	store := &sessionjwt.MemoryJTIStore{}
	ctx := context.Background()
	if err := store.RevokeAccess(ctx, "jti-exp", 5*time.Millisecond); err != nil {
		t.Fatal(err)
	}
	time.Sleep(15 * time.Millisecond)
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

func TestRedisJTIStore_EmptyIDNoOps(t *testing.T) {
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
}

func TestRedisJTIStore_SessionOnlyRevoke(t *testing.T) {
	t.Parallel()
	store, _ := redisStore(t)
	ctx := context.Background()
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
	first, err := store.ConsumeStepUp(ctx, "step-z", 0)
	requireConsume(t, consumeResult{first, err}, true, "step zero")
	if err := store.RevokeSessionAndFamily(ctx, "sid-ms", "fam-ms", 500*time.Microsecond); err != nil {
		t.Fatal(err)
	}
}

func TestRedisJTIStore_ConsumeOnceErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if _, err := store.ConsumeOnce(context.Background(), "j", time.Minute); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_RevokeFamilyErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if err := store.RevokeFamily(context.Background(), "f", time.Minute); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_FamilyRevokedErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if _, err := store.FamilyRevoked(context.Background(), "f"); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_RevokeSessionErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if err := store.RevokeSession(context.Background(), "s", time.Minute); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_RevokeSessionAndFamilyErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if err := store.RevokeSessionAndFamily(context.Background(), "s", "f", time.Minute); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_SessionRevokedErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if _, err := store.SessionRevoked(context.Background(), "s"); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_RevokeAccessErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if err := store.RevokeAccess(context.Background(), "j", time.Minute); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_AccessRevokedErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if _, err := store.AccessRevoked(context.Background(), "j"); err == nil {
		t.Fatal("expected error")
	}
}

func TestRedisJTIStore_ConsumeStepUpErrorsAfterClose(t *testing.T) {
	t.Parallel()
	store, mr := redisStore(t)
	mr.Close()
	if _, err := store.ConsumeStepUp(context.Background(), "s", time.Minute); err == nil {
		t.Fatal("expected error")
	}
}
