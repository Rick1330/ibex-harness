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

func TestUnit_Cache_HitMissError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	agent := uuid.MustParse("22222222-2222-2222-2222-222222222222")
	ext := "33333333-3333-3333-3333-333333333333"
	sid := uuid.MustParse("44444444-4444-4444-4444-444444444444")

	if _, ok := cache.Get(context.Background(), org, agent, ext); ok {
		t.Fatal("expected miss")
	}

	cache.Set(context.Background(), org, agent, ext, sessioncache.Entry{
		SessionID: sid, TurnCount: 3,
	})
	got, ok := cache.Get(context.Background(), org, agent, ext)
	if !ok {
		t.Fatal("expected hit")
	}
	if got.SessionID != sid || got.TurnCount != 3 {
		t.Fatalf("got=%+v", got)
	}

	wantKey := org.String() + ":session:" + agent.String() + ":" + ext
	if sessioncache.Key(org, agent, ext) != wantKey {
		t.Fatalf("key=%s", sessioncache.Key(org, agent, ext))
	}

	mr.Set(wantKey, "{")
	if _, ok := cache.Get(context.Background(), org, agent, ext); ok {
		t.Fatal("corrupt should miss")
	}

	mr.Close()
	if _, ok := cache.Get(context.Background(), org, agent, ext); ok {
		t.Fatal("redis down should miss")
	}
}

func TestUnit_Cache_Invalidate(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	ext := uuid.New().String()
	cache.Set(context.Background(), org, agent, ext, sessioncache.Entry{
		SessionID: uuid.New(), TurnCount: 1,
	})
	cache.Invalidate(context.Background(), org, agent, ext)
	if _, ok := cache.Get(context.Background(), org, agent, ext); ok {
		t.Fatal("expected miss after invalidate")
	}
}

func TestUnit_Cache_SetGuards(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	org, agent := uuid.New(), uuid.New()
	cache.Set(context.Background(), org, agent, "", sessioncache.Entry{SessionID: uuid.New()})
	cache.Set(context.Background(), org, agent, "e", sessioncache.Entry{})
	var nilCache *sessioncache.Cache
	nilCache.Set(context.Background(), org, agent, "e", sessioncache.Entry{SessionID: uuid.New()})
	nilCache.Invalidate(context.Background(), org, agent, "e")
	if _, ok := nilCache.Get(context.Background(), org, agent, "e"); ok {
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
