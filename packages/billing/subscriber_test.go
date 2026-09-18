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

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

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

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumPat(context.Background()).Result()
		if err == nil && n > 0 {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	n, err := client.PubSubNumPat(context.Background()).Result()
	if err != nil || n == 0 {
		t.Fatal("pubsub pattern not registered")
	}

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

	deadline = time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if _, _, err := cache.Check(context.Background(), org); err != nil {
			t.Fatal(err)
		}
		if loader.callCount() >= 2 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("cache not invalidated; loader.calls=%d", loader.callCount())
}
