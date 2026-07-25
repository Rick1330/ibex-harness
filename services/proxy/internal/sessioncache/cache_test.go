package sessioncache_test

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func testCache(t *testing.T) (*sessioncache.Cache, *miniredis.Miniredis) {
	t.Helper()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	return cache, mr
}

func TestUnit_Cache_MissThenHit(t *testing.T) {
	t.Parallel()

	cache, _ := testCache(t)
	key := sessioncache.LookupKey{
		OrgID:      uuid.MustParse("11111111-1111-1111-1111-111111111111"),
		AgentID:    uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		ExternalID: "33333333-3333-3333-3333-333333333333",
	}
	sid := uuid.MustParse("44444444-4444-4444-4444-444444444444")

	if _, ok := cache.Get(context.Background(), key); ok {
		t.Fatal("expected miss")
	}

	cache.Set(context.Background(), key, sessioncache.Entry{SessionID: sid, TurnCount: 3})

	got, ok := cache.Get(context.Background(), key)
	if !ok {
		t.Fatal("expected hit")
	}
	if got.SessionID != sid {
		t.Fatalf("session_id=%s", got.SessionID)
	}
	if got.TurnCount != 3 {
		t.Fatalf("turn_count=%d", got.TurnCount)
	}
	if got.Version != sessioncache.EntryVersion {
		t.Fatalf("version=%d", got.Version)
	}

	wantKey := "session:" + key.OrgID.String() + ":" + key.AgentID.String() + ":" + key.ExternalID
	if sessioncache.Key(key) != wantKey {
		t.Fatalf("key=%s", sessioncache.Key(key))
	}
}

func TestUnit_Cache_CorruptAndDownMiss(t *testing.T) {
	t.Parallel()

	cache, mr := testCache(t)
	key := sessioncache.LookupKey{
		OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: uuid.New().String(),
	}

	if err := mr.Set(sessioncache.Key(key), "{"); err != nil {
		t.Fatal(err)
	}
	if _, ok := cache.Get(context.Background(), key); ok {
		t.Fatal("corrupt should miss")
	}

	mr.Close()
	if _, ok := cache.Get(context.Background(), key); ok {
		t.Fatal("redis down should miss")
	}
}

func TestUnit_Cache_VersionMismatchMiss(t *testing.T) {
	t.Parallel()

	cache, mr := testCache(t)
	key := sessioncache.LookupKey{
		OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: "e",
	}
	if err := mr.Set(sessioncache.Key(key), `{"v":99,"session_id":"44444444-4444-4444-4444-444444444444","turn_count":1}`); err != nil {
		t.Fatal(err)
	}
	if _, ok := cache.Get(context.Background(), key); ok {
		t.Fatal("bad version should miss")
	}
}

func TestUnit_Cache_Invalidate(t *testing.T) {
	t.Parallel()

	cache, _ := testCache(t)
	key := sessioncache.LookupKey{
		OrgID: uuid.New(), AgentID: uuid.New(), ExternalID: uuid.New().String(),
	}

	cache.Set(context.Background(), key, sessioncache.Entry{
		SessionID: uuid.New(), TurnCount: 1,
	})
	cache.Invalidate(context.Background(), key)

	if _, ok := cache.Get(context.Background(), key); ok {
		t.Fatal("expected miss after invalidate")
	}
}

func TestUnit_Cache_SetGuards(t *testing.T) {
	t.Parallel()

	cache, _ := testCache(t)
	org, agent := uuid.New(), uuid.New()

	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "",
	}, sessioncache.Entry{SessionID: uuid.New()})
	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "e",
	}, sessioncache.Entry{})

	var nilCache *sessioncache.Cache
	nilCache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "e",
	}, sessioncache.Entry{SessionID: uuid.New()})
	nilCache.Invalidate(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "e",
	})
	if _, ok := nilCache.Get(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: "e",
	}); ok {
		t.Fatal("nil cache get")
	}
}

func TestUnit_Cache_NewValidation(t *testing.T) {
	t.Parallel()

	if _, err := sessioncache.New(nil, time.Second); err == nil {
		t.Fatal("expected nil client error")
	}

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	if _, err := sessioncache.New(client, 0); err == nil {
		t.Fatal("expected ttl error")
	}
}
