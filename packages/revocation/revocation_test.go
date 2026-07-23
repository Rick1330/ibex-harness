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
	assertEventValid(t, sampleEvent("tok-1"))
	assertEventInvalid(t, revocation.RevocationEvent{Version: 2, TokenID: "x", OrgID: "o", RevokedAt: time.Now()})
	assertEventInvalid(t, revocation.RevocationEvent{Version: 1, OrgID: "o", RevokedAt: time.Now()})
	assertEventInvalid(t, revocation.RevocationEvent{Version: 1, TokenID: "t", RevokedAt: time.Now()})
	assertEventInvalid(t, revocation.RevocationEvent{Version: 1, TokenID: "t", OrgID: "o"})
}

func assertEventValid(t *testing.T, e revocation.RevocationEvent) {
	t.Helper()
	if err := e.Validate(); err != nil {
		t.Fatalf("valid: %v", err)
	}
}

func assertEventInvalid(t *testing.T, e revocation.RevocationEvent) {
	t.Helper()
	if err := e.Validate(); err == nil {
		t.Fatal("expected validation error")
	}
}

func sampleEvent(tokenID string) revocation.RevocationEvent {
	return revocation.RevocationEvent{
		Version: 1, TokenID: tokenID, OrgID: "org-1", RevokedAt: time.Now().UTC(),
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

func newTestRedis(t *testing.T) (*miniredis.Miniredis, *redis.Client) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return mr, client
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
	_, client := newTestRedis(t)
	metrics := &countingPublishMetrics{}
	pub := mustPublisher(t, client, metrics)
	sub := subscribeChannel(t, client)
	mustPublish(t, pub, sampleEvent("tok-1"))
	assertPublishedToken(t, sub, "tok-1")
	assertPublishOKMetric(t, metrics)
}

func mustPublisher(t *testing.T, client *redis.Client, m revocation.PublishMetrics) *revocation.RedisPublisher {
	t.Helper()
	pub, err := revocation.NewRedisPublisher(client, logger.Discard("revocation"), m)
	if err != nil {
		t.Fatalf("NewRedisPublisher: %v", err)
	}
	return pub
}

func mustPublish(t *testing.T, pub *revocation.RedisPublisher, event revocation.RevocationEvent) {
	t.Helper()
	if err := pub.Publish(context.Background(), event); err != nil {
		t.Fatalf("Publish: %v", err)
	}
}

func assertPublishOKMetric(t *testing.T, m *countingPublishMetrics) {
	t.Helper()
	if m.ok.Load() != 1 {
		t.Fatalf("ok metric=%d", m.ok.Load())
	}
}

func assertPublishedToken(t *testing.T, sub *redis.PubSub, wantID string) {
	t.Helper()
	select {
	case msg := <-sub.Channel():
		assertPayloadTokenID(t, msg.Payload, wantID)
	case <-time.After(time.Second):
		t.Fatal("timeout waiting for publish")
	}
}

func assertPayloadTokenID(t *testing.T, payload, wantID string) {
	t.Helper()
	got, err := revocation.ParseEvent(payload)
	if err != nil {
		t.Fatalf("parse payload: %v", err)
	}
	if got.TokenID != wantID {
		t.Fatalf("token_id=%q", got.TokenID)
	}
}

func TestUnit_RedisPublisherRejectsBadEvent(t *testing.T) {
	t.Parallel()
	_, client := newTestRedis(t)
	pub := mustPublisher(t, client, nil)
	err := pub.Publish(context.Background(), revocation.RevocationEvent{Version: 1})
	if err == nil {
		t.Fatal("expected validation error")
	}
}

func TestUnit_RedisPublisherRedisFailure(t *testing.T) {
	t.Parallel()
	mr, client := newTestRedis(t)
	metrics := &countingPublishMetrics{}
	pub := mustPublisher(t, client, metrics)
	mr.Close()
	err := pub.Publish(context.Background(), sampleEvent("tok-fail"))
	if err == nil {
		t.Fatal("expected publish error")
	}
	if metrics.fail.Load() != 1 {
		t.Fatalf("fail metric=%d", metrics.fail.Load())
	}
}

type spyInvalidator struct {
	mu     sync.Mutex
	ids    []string
	hits   atomic.Int64
	signal chan string
}

func newSpyInvalidator() *spyInvalidator {
	return &spyInvalidator{signal: make(chan string, 8)}
}

func (s *spyInvalidator) InvalidateByTokenID(tokenID string) {
	s.hits.Add(1)
	s.mu.Lock()
	s.ids = append(s.ids, tokenID)
	s.mu.Unlock()
	select {
	case s.signal <- tokenID:
	default:
	}
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
	_, client := newTestRedis(t)
	inv := newSpyInvalidator()
	metrics := &countingInvalidateMetrics{}
	sub := startSubscriber(t, client, inv, metrics)
	publishRaw(t, client, sampleEvent("tok-xyz"))
	waitInvalidate(t, inv, "tok-xyz")
	sub.Stop()
	if metrics.n.Load() < 1 {
		t.Fatal("expected invalidate metric")
	}
}

func publishRaw(t *testing.T, client *redis.Client, event revocation.RevocationEvent) {
	t.Helper()
	raw, err := event.Marshal()
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if err := client.Publish(context.Background(), revocation.Channel, raw).Err(); err != nil {
		t.Fatalf("publish: %v", err)
	}
}

func waitInvalidate(t *testing.T, inv *spyInvalidator, wantID string) {
	t.Helper()
	select {
	case got := <-inv.signal:
		if got != wantID {
			t.Fatalf("token_id=%q want %q", got, wantID)
		}
	case <-time.After(time.Second):
		t.Fatalf("timeout waiting for invalidate; hits=%d", inv.hits.Load())
	}
}

func TestUnit_SubscriberSkipsMalformed(t *testing.T) {
	t.Parallel()
	_, client := newTestRedis(t)
	inv := newSpyInvalidator()
	sub := startSubscriber(t, client, inv, nil)
	if err := client.Publish(context.Background(), revocation.Channel, "{").Err(); err != nil {
		t.Fatalf("publish: %v", err)
	}
	publishRaw(t, client, sampleEvent("sentinel"))
	waitInvalidate(t, inv, "sentinel")
	sub.Stop()
	if inv.hits.Load() != 1 {
		t.Fatalf("hits=%d want 1 (malformed skipped)", inv.hits.Load())
	}
}

func TestUnit_SubscriberStopsOnContextCancel(t *testing.T) {
	t.Parallel()
	_, client := newTestRedis(t)
	inv := newSpyInvalidator()
	sub, err := revocation.NewSubscriber(client, inv, logger.Discard("revocation"), nil)
	if err != nil {
		t.Fatalf("NewSubscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	go sub.Run(ctx)
	waitForSubscribe(t, client)
	cancel()
	waitSubscriberDone(t, sub)
}

func TestUnit_SubscriberStopAfterRun(t *testing.T) {
	t.Parallel()
	_, client := newTestRedis(t)
	sub := startSubscriber(t, client, newSpyInvalidator(), nil)
	sub.Stop()
	waitSubscriberDone(t, sub)
}

func waitSubscriberDone(t *testing.T, sub *revocation.Subscriber) {
	t.Helper()
	select {
	case <-sub.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("subscriber did not exit")
	}
}

func TestUnit_SubscriberReconnectAfterDisconnect(t *testing.T) {
	t.Parallel()
	mr, client := newTestRedis(t)
	inv := newSpyInvalidator()
	sub, err := revocation.NewSubscriber(client, inv, logger.Discard("revocation"), nil)
	if err != nil {
		t.Fatalf("NewSubscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)
	waitForSubscribe(t, client)
	mr.Close()
	// Force reconnect path; cancel soon so sleepBackoff exits without long wait.
	time.AfterFunc(50*time.Millisecond, cancel)
	waitSubscriberDone(t, sub)
}

func TestUnit_NewSubscriberRequiresDeps(t *testing.T) {
	t.Parallel()
	_, client := newTestRedis(t)
	inv := newSpyInvalidator()
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
	deadline := time.After(2 * time.Second)
	ticker := time.NewTicker(10 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-deadline:
			t.Fatal("subscriber did not attach in time")
		case <-ticker.C:
			n, err := client.PubSubNumSub(context.Background(), revocation.Channel).Result()
			if err == nil && n[revocation.Channel] > 0 {
				return
			}
		}
	}
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
	_, client := newTestRedis(t)
	_, err = revocation.NewRedisPublisher(client, nil, nil)
	if err == nil {
		t.Fatal("expected logger error")
	}
}
