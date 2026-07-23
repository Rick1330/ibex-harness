package revocation_test

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/revocation"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestUnit_RevocationEventValidate(t *testing.T) {
	t.Parallel()
	ok := revocation.RevocationEvent{Version: 1, TokenID: "tok-1"}
	if err := ok.Validate(); err != nil {
		t.Fatalf("valid: %v", err)
	}
	if err := (revocation.RevocationEvent{Version: 2, TokenID: "x"}).Validate(); err == nil {
		t.Fatal("expected version error")
	}
	if err := (revocation.RevocationEvent{Version: 1}).Validate(); err == nil {
		t.Fatal("expected token_id error")
	}
}

func TestUnit_ParseEventRoundTrip(t *testing.T) {
	t.Parallel()
	in := revocation.RevocationEvent{
		Version:   1,
		TokenID:   "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
		OrgID:     "org-1",
		RevokedAt: time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC),
	}
	raw, err := in.Marshal()
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	out, err := revocation.ParseEvent(string(raw))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if out.TokenID != in.TokenID || out.OrgID != in.OrgID {
		t.Fatalf("got %+v want %+v", out, in)
	}
}

func TestUnit_ParseEventMalformed(t *testing.T) {
	t.Parallel()
	if _, err := revocation.ParseEvent("{"); err == nil {
		t.Fatal("expected decode error")
	}
}

type countingPublishMetrics struct {
	ok, fail atomic.Int64
}

func (m *countingPublishMetrics) IncRevocationPublish(result string) {
	if result == "ok" {
		m.ok.Add(1)
		return
	}
	m.fail.Add(1)
}

func TestUnit_RedisPublisherPublish(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	metrics := &countingPublishMetrics{}
	pub, err := revocation.NewRedisPublisher(client, logger.Discard("revocation"), metrics)
	if err != nil {
		t.Fatalf("NewRedisPublisher: %v", err)
	}
	sub := client.Subscribe(context.Background(), revocation.Channel)
	t.Cleanup(func() { _ = sub.Close() })
	if _, err := sub.Receive(context.Background()); err != nil {
		t.Fatalf("subscribe: %v", err)
	}

	event := revocation.RevocationEvent{
		Version: 1, TokenID: "tok-1", OrgID: "org-1", RevokedAt: time.Now().UTC(),
	}
	if err := pub.Publish(context.Background(), event); err != nil {
		t.Fatalf("Publish: %v", err)
	}
	select {
	case msg := <-sub.Channel():
		got, err := revocation.ParseEvent(msg.Payload)
		if err != nil {
			t.Fatalf("parse payload: %v", err)
		}
		if got.TokenID != "tok-1" {
			t.Fatalf("token_id=%q", got.TokenID)
		}
	case <-time.After(time.Second):
		t.Fatal("timeout waiting for publish")
	}
	if metrics.ok.Load() != 1 {
		t.Fatalf("ok metric=%d", metrics.ok.Load())
	}
}

func TestUnit_RedisPublisherRejectsBadEvent(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	pub, err := revocation.NewRedisPublisher(client, logger.Discard("revocation"), nil)
	if err != nil {
		t.Fatalf("NewRedisPublisher: %v", err)
	}
	err = pub.Publish(context.Background(), revocation.RevocationEvent{Version: 1})
	if err == nil {
		t.Fatal("expected validation error")
	}
}

type spyInvalidator struct {
	mu   sync.Mutex
	ids  []string
	hits atomic.Int64
}

func (s *spyInvalidator) InvalidateByTokenID(tokenID string) {
	s.hits.Add(1)
	s.mu.Lock()
	s.ids = append(s.ids, tokenID)
	s.mu.Unlock()
}

type countingInvalidateMetrics struct {
	n atomic.Int64
}

func (m *countingInvalidateMetrics) IncRevocationInvalidate() { m.n.Add(1) }

func TestUnit_SubscriberInvalidatesOnMessage(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	inv := &spyInvalidator{}
	metrics := &countingInvalidateMetrics{}
	sub, err := revocation.NewSubscriber(client, inv, logger.Discard("revocation"), metrics)
	if err != nil {
		t.Fatalf("NewSubscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)

	waitForSubscribe(t, client)

	pub := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = pub.Close() })
	event := revocation.RevocationEvent{
		Version: 1, TokenID: "tok-xyz", OrgID: "org", RevokedAt: time.Now().UTC(),
	}
	raw, err := event.Marshal()
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := pub.Publish(context.Background(), revocation.Channel, raw).Err(); err != nil {
		t.Fatalf("publish: %v", err)
	}

	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if inv.hits.Load() >= 1 {
			break
		}
		time.Sleep(5 * time.Millisecond)
	}
	sub.Stop()
	if inv.hits.Load() < 1 {
		t.Fatal("expected InvalidateByTokenID")
	}
	if metrics.n.Load() < 1 {
		t.Fatal("expected invalidate metric")
	}
}

func TestUnit_SubscriberSkipsMalformed(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })

	inv := &spyInvalidator{}
	sub, err := revocation.NewSubscriber(client, inv, logger.Discard("revocation"), nil)
	if err != nil {
		t.Fatalf("NewSubscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)
	waitForSubscribe(t, client)

	pub := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = pub.Close() })
	if err := pub.Publish(context.Background(), revocation.Channel, "{").Err(); err != nil {
		t.Fatalf("publish: %v", err)
	}
	time.Sleep(50 * time.Millisecond)
	sub.Stop()
	if inv.hits.Load() != 0 {
		t.Fatalf("hits=%d want 0", inv.hits.Load())
	}
}

func waitForSubscribe(t *testing.T, client *redis.Client) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumSub(context.Background(), revocation.Channel).Result()
		if err == nil && n[revocation.Channel] > 0 {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("subscriber did not attach in time")
}

func TestUnit_NoopPublisher(t *testing.T) {
	t.Parallel()
	if err := (revocation.NoopPublisher{}).Publish(context.Background(), revocation.RevocationEvent{}); err != nil {
		t.Fatalf("noop: %v", err)
	}
}

func TestUnit_NewRedisPublisherRequiresDeps(t *testing.T) {
	t.Parallel()
	_, err := revocation.NewRedisPublisher(nil, logger.Discard("x"), nil)
	if err == nil {
		t.Fatal("expected error")
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	_, err = revocation.NewRedisPublisher(client, nil, nil)
	if err == nil {
		t.Fatal("expected logger error")
	}
}
