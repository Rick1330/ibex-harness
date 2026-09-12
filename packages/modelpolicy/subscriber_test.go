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

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

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
	waitPubSubPatterns(t, client)

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
