package modelpolicy

import (
	"context"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestRedisPublisher_PublishRoundTrip(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	pub, err := NewRedisPublisher(client, logger.Discard("mp-pub"))
	if err != nil {
		t.Fatal(err)
	}
	org := uuid.New()
	if err := pub.Publish(context.Background(), InvalidateEvent{
		Version: CurrentEventVersion,
		OrgID:   org.String(),
	}); err != nil {
		t.Fatal(err)
	}
}

func TestNewRedisPublisher_RequiresDeps(t *testing.T) {
	t.Parallel()
	if _, err := NewRedisPublisher(nil, logger.Discard("x")); err == nil {
		t.Fatal("expected nil client error")
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	if _, err := NewRedisPublisher(client, nil); err == nil {
		t.Fatal("expected nil logger error")
	}
}

func TestNoopPublisher(t *testing.T) {
	t.Parallel()
	if err := (NoopPublisher{}).Publish(context.Background(), InvalidateEvent{}); err != nil {
		t.Fatal(err)
	}
}

func TestNewCache_NilLoader(t *testing.T) {
	t.Parallel()
	if _, err := NewCache(nil, Config{}, NoopMetrics{}); err == nil {
		t.Fatal("expected error")
	}
}

func TestNewOrgAwareRegistry_RequiresDeps(t *testing.T) {
	t.Parallel()
	if _, err := NewOrgAwareRegistry(nil, nil, nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestNewSubscriber_RequiresDeps(t *testing.T) {
	t.Parallel()
	if _, err := NewSubscriber(nil, nil, nil, nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestInvalidate_NilOrgNoop(t *testing.T) {
	t.Parallel()
	cache, err := NewCache(&fakeLoader{policies: map[uuid.UUID][]Policy{}}, Config{LRUSize: 4}, NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	cache.Invalidate(uuid.Nil)
}
