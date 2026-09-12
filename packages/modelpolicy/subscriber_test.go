package modelpolicy

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestSubscriber_PubSubInvalidatesWithinOneSecond(t *testing.T) {
	org := uuid.New()
	cache, loader := seedCachedDeny(t, org)
	client := newMiniRedis(t)
	startSubscriber(t, client, cache)
	waitPubSubPatterns(t, client)
	mustPublishInvalidate(t, client, org)
	assertReloaded(t, cache, loader, org)
}

func seedCachedDeny(t *testing.T, org uuid.UUID) (*Cache, *fakeLoader) {
	t.Helper()
	loader := &fakeLoader{policies: map[uuid.UUID][]Policy{
		org: {{Pattern: "claude-*", Allowed: false, Priority: 1}},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Hour, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.calls != 1 {
		t.Fatalf("calls=%d", loader.calls)
	}
	return cache, loader
}

func newMiniRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func startSubscriber(t *testing.T, client redis.UniversalClient, cache Invalidator) {
	t.Helper()
	sub, err := NewSubscriber(client, cache, logger.Discard("modelpolicy-test"), NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go sub.Run(ctx)
	t.Cleanup(func() {
		sub.Stop()
		<-sub.Done()
	})
}

func mustPublishInvalidate(t *testing.T, client redis.UniversalClient, org uuid.UUID) {
	t.Helper()
	pub, err := NewRedisPublisher(client, logger.Discard("modelpolicy-test"))
	if err != nil {
		t.Fatal(err)
	}
	if err := pub.Publish(context.Background(), InvalidateEvent{
		Version: CurrentEventVersion,
		OrgID:   org.String(),
	}); err != nil {
		t.Fatal(err)
	}
}

func assertReloaded(t *testing.T, cache *Cache, loader *fakeLoader, org uuid.UUID) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if _, err := cache.PoliciesForOrg(context.Background(), org); err != nil {
			t.Fatal(err)
		}
		if loader.calls >= 2 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("cache not invalidated within 1s; loader.calls=%d", loader.calls)
}

func waitPubSubPatterns(t *testing.T, client redis.UniversalClient) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumPat(context.Background()).Result()
		if err == nil && n > 0 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("pubsub pattern not registered within 2s")
}
