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
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	org := uuid.New()
	channel := ChannelForOrg(org)
	pubsub := client.Subscribe(context.Background(), channel)
	t.Cleanup(func() { _ = pubsub.Close() })
	if _, err := pubsub.Receive(context.Background()); err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	msgCh := pubsub.Channel()

	pub, err := NewRedisPublisher(client, logger.Discard("mp-pub"))
	if err != nil {
		t.Fatal(err)
	}
	want := InvalidateEvent{Version: CurrentEventVersion, OrgID: org.String()}
	if err := pub.Publish(context.Background(), want); err != nil {
		t.Fatal(err)
	}
	select {
	case msg := <-msgCh:
		got, err := ParseInvalidateEvent(msg.Payload)
		if err != nil {
			t.Fatal(err)
		}
		if got.Version != want.Version || got.OrgID != want.OrgID {
			t.Fatalf("got=%+v want=%+v", got, want)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for published message")
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
