package billing

import (
	"context"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestStartInvalidateSubscriber_PublishesInvalidate(t *testing.T) {
	org, loader, cache := warmBudgetCache(t)
	client := newMiniRedisClient(t)
	startInvalidateSub(t, client, cache)
	waitPubSubPatterns(t, client)
	publishOrgInvalidate(t, client, org)
	cacheReloadWait{cache: cache, loader: loader, org: org, wantCalls: 2}.until(t)
}

func warmBudgetCache(t *testing.T) (uuid.UUID, *fakeBudgetLoader, *Cache) {
	t.Helper()
	org := uuid.New()
	loader := &fakeBudgetLoader{snaps: map[uuid.UUID]BudgetSnapshot{
		org: {HasHardCap: true, CapCents: 1000, SpentCents: 10, EnforcementMode: EnforcementHardCap},
	}}
	cache, err := NewCache(loader, Config{CacheTTL: time.Hour, LRUSize: 8}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := cache.Check(context.Background(), org); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 1 {
		t.Fatalf("warmup calls=%d", loader.callCount())
	}
	return org, loader, cache
}

func newMiniRedisClient(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func startInvalidateSub(t *testing.T, client *redis.Client, cache *Cache) {
	t.Helper()
	sub, err := StartInvalidateSubscriber(client, cache, logger.Discard("billing-test"))
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go sub.Run(ctx, "billing-test")
	t.Cleanup(func() {
		sub.Stop()
		<-sub.Done()
	})
}

func waitPubSubPatterns(t *testing.T, client *redis.Client) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumPat(context.Background()).Result()
		if err == nil && n > 0 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("pubsub pattern not registered")
}

func publishOrgInvalidate(t *testing.T, client *redis.Client, org uuid.UUID) {
	t.Helper()
	payload, err := MarshalInvalidate(InvalidateEvent{
		Version: CurrentEventVersion,
		OrgID:   org.String(),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := client.Publish(context.Background(), ChannelForOrg(org), string(payload)).Err(); err != nil {
		t.Fatal(err)
	}
}

type cacheReloadWait struct {
	cache     *Cache
	loader    *fakeBudgetLoader
	org       uuid.UUID
	wantCalls int
}

func (w cacheReloadWait) until(t *testing.T) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if _, _, err := w.cache.Check(context.Background(), w.org); err != nil {
			t.Fatal(err)
		}
		if w.loader.callCount() >= w.wantCalls {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("cache not invalidated; loader.calls=%d", w.loader.callCount())
}
