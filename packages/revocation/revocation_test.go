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
	assertEventFields(t, out, in.TokenID, in.OrgID)
}

func assertEventFields(t *testing.T, got revocation.RevocationEvent, tokenID, orgID string) {
	t.Helper()
	if got.TokenID != tokenID {
		t.Fatalf("token_id=%q want %q", got.TokenID, tokenID)
	}
	if got.OrgID != orgID {
		t.Fatalf("org_id=%q want %q", got.OrgID, orgID)
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

func newTestRedis(t *testing.T) *redis.Client {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return client
}

func subscribeChannel(t *testing.T, client *redis.Client) *redis.PubSub {
	t.Helper()
	sub := client.Subscribe(context.Background(), revocation.Channel)
	t.Cleanup(func() { _ = sub.Close() })
	if _, err := sub.Receive(context.Background()); err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	return sub
}

func TestUnit_RedisPublisherPublish(t *testing.T) {
	t.Parallel()
	client := newTestRedis(t)
	metrics := &countingPublishMetrics{}
	pub, err := revocation.NewRedisPublisher(client, logger.Discard("revocation"), metrics)
	if err != nil {
		t.Fatalf("NewRedisPublisher: %v", err)
	}
	sub := subscribeChannel(t, client)
	event := revocation.RevocationEvent{
		Version: 1, TokenID: "tok-1", OrgID: "org-1", RevokedAt: time.Now().UTC(),
	}
	if err := pub.Publish(context.Background(), event); err != nil {
		t.Fatalf("Publish: %v", err)
	}
	assertPublishedToken(t, sub, "tok-1")
	if metrics.ok.Load() != 1 {
		t.Fatalf("ok metric=%d", metrics.ok.Load())
	}
}

func assertPublishedToken(t *testing.T, sub *redis.PubSub, wantID string) {
	t.Helper()
	select {
	case msg := <-sub.Channel():
		got, err := revocation.ParseEvent(msg.Payload)
		if err != nil {
			t.Fatalf("parse payload: %v", err)
		}
		if got.TokenID != wantID {
			t.Fatalf("token_id=%q", got.TokenID)
		}
	case <-time.After(time.Second):
		t.Fatal("timeout waiting for publish")
	}
}

func TestUnit_RedisPublisherRejectsBadEvent(t *testing.T) {
	t.Parallel()
	client := newTestRedis(t)
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

func startSubscriber(t *testing.T, client *redis.Client, inv revocation.Invalidator, metrics revocation.InvalidateMetrics) *revocation.Subscriber {
	t.Helper()
	sub, err := revocation.NewSubscriber(client, inv, logger.Discard("revocation"), metrics)
	if err != nil {
		t.Fatalf("NewSubscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go sub.Run(ctx)
	waitForSubscribe(t, client)
	return sub
}

func TestUnit_SubscriberInvalidatesOnMessage(t *testing.T) {
	t.Parallel()
	client := newTestRedis(t)
	inv := &spyInvalidator{}
	metrics := &countingInvalidateMetrics{}
	sub := startSubscriber(t, client, inv, metrics)

	event := revocation.RevocationEvent{
		Version: 1, TokenID: "tok-xyz", OrgID: "org", RevokedAt: time.Now().UTC(),
	}
	raw, err := event.Marshal()
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := client.Publish(context.Background(), revocation.Channel, raw).Err(); err != nil {
		t.Fatalf("publish: %v", err)
	}
	waitHits(t, inv, 1)
	sub.Stop()
	if metrics.n.Load() < 1 {
		t.Fatal("expected invalidate metric")
	}
}

func waitHits(t *testing.T, inv *spyInvalidator, want int64) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if inv.hits.Load() >= want {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatalf("hits=%d want >= %d", inv.hits.Load(), want)
}

func TestUnit_SubscriberSkipsMalformed(t *testing.T) {
	t.Parallel()
	client := newTestRedis(t)
	inv := &spyInvalidator{}
	sub := startSubscriber(t, client, inv, nil)
	if err := client.Publish(context.Background(), revocation.Channel, "{").Err(); err != nil {
		t.Fatalf("publish: %v", err)
	}
	time.Sleep(50 * time.Millisecond)
	sub.Stop()
	if inv.hits.Load() != 0 {
		t.Fatalf("hits=%d want 0", inv.hits.Load())
	}
}

func TestUnit_NewSubscriberRequiresDeps(t *testing.T) {
	t.Parallel()
	client := newTestRedis(t)
	inv := &spyInvalidator{}
	log := logger.Discard("revocation")
	if _, err := revocation.NewSubscriber(nil, inv, log, nil); err == nil {
		t.Fatal("expected client error")
	}
	if _, err := revocation.NewSubscriber(client, nil, log, nil); err == nil {
		t.Fatal("expected cache error")
	}
	if _, err := revocation.NewSubscriber(client, inv, nil, nil); err == nil {
		t.Fatal("expected logger error")
	}
}

func waitForSubscribe(t *testing.T, client *redis.Client) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumSub(context.Background(), revocation.Channel).Result()
		if err != nil {
			time.Sleep(10 * time.Millisecond)
			continue
		}
		if n[revocation.Channel] > 0 {
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
	client := newTestRedis(t)
	_, err = revocation.NewRedisPublisher(client, nil, nil)
	if err == nil {
		t.Fatal("expected logger error")
	}
}
