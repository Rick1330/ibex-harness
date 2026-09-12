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

func TestRedisPublisher_PublishRoundTrip(t *testing.T) {
	t.Parallel()
	client := newPublisherMiniRedis(t)
	org := uuid.New()
	msgCh := subscribeOrgChannel(t, client, org)
	pub := mustRedisPublisher(t, client)
	want := InvalidateEvent{Version: CurrentEventVersion, OrgID: org.String()}
	if err := pub.Publish(context.Background(), want); err != nil {
		t.Fatal(err)
	}
	assertPublishedEvent(t, msgCh, want)
}

func newPublisherMiniRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func subscribeOrgChannel(t *testing.T, client *redis.Client, org uuid.UUID) <-chan *redis.Message {
	t.Helper()
	pubsub := client.Subscribe(context.Background(), ChannelForOrg(org))
	t.Cleanup(func() { _ = pubsub.Close() })
	if _, err := pubsub.Receive(context.Background()); err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	return pubsub.Channel()
}

func mustRedisPublisher(t *testing.T, client *redis.Client) *RedisPublisher {
	t.Helper()
	pub, err := NewRedisPublisher(client, logger.Discard("mp-pub"))
	if err != nil {
		t.Fatal(err)
	}
	return pub
}

func assertPublishedEvent(t *testing.T, msgCh <-chan *redis.Message, want InvalidateEvent) {
	t.Helper()
	select {
	case msg := <-msgCh:
		assertInvalidatePayload(t, msg.Payload, want)
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for published message")
	}
}

func assertInvalidatePayload(t *testing.T, payload string, want InvalidateEvent) {
	t.Helper()
	got, err := ParseInvalidateEvent(payload)
	if err != nil {
		t.Fatal(err)
	}
	if got.Version != want.Version || got.OrgID != want.OrgID {
		t.Fatalf("got=%+v want=%+v", got, want)
	}
}

func TestNewRedisPublisher_RequiresDeps(t *testing.T) {
	t.Parallel()
	if _, err := NewRedisPublisher(nil, logger.Discard("x")); err == nil {
		t.Fatal("expected nil client error")
	}
	client := newPublisherMiniRedis(t)
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
