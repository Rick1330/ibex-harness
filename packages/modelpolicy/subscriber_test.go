package modelpolicy

import (
	"context"
	"sync"
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

func TestSubscriber_MalformedPayloadIgnored(t *testing.T) {
	warmOrg := uuid.New()
	cache, loader := seedCachedDeny(t, warmOrg)
	rec := &recordingInvalidator{inner: cache, seen: make(chan uuid.UUID, 4)}
	client := newMiniRedis(t)
	startSubscriber(t, client, rec)
	waitPubSubPatterns(t, client)

	if err := client.Publish(context.Background(), ChannelForOrg(warmOrg), `{`).Err(); err != nil {
		t.Fatal(err)
	}
	other := uuid.New()
	bad := `{"v":1,"org_id":"` + other.String() + `"}`
	if err := client.Publish(context.Background(), ChannelForOrg(warmOrg), bad).Err(); err != nil {
		t.Fatal(err)
	}

	sentinel := uuid.New()
	mustPublishInvalidate(t, client, sentinel)
	waitInvalidated(t, rec, sentinel)

	if got := rec.orgsSnapshot(); len(got) != 1 || got[0] != sentinel {
		t.Fatalf("invalidated=%v want only sentinel %s", got, sentinel)
	}
	if loader.callCount() != 1 {
		t.Fatalf("warm org must not reload; calls=%d", loader.callCount())
	}
	if _, err := cache.PoliciesForOrg(context.Background(), warmOrg); err != nil {
		t.Fatal(err)
	}
	if loader.callCount() != 1 {
		t.Fatalf("cache should still be warm; calls=%d", loader.callCount())
	}
}

type recordingInvalidator struct {
	inner Invalidator
	seen  chan uuid.UUID
	mu    sync.Mutex
	orgs  []uuid.UUID
}

func (r *recordingInvalidator) Invalidate(orgID uuid.UUID) {
	r.mu.Lock()
	r.orgs = append(r.orgs, orgID)
	r.mu.Unlock()
	if r.inner != nil {
		r.inner.Invalidate(orgID)
	}
	select {
	case r.seen <- orgID:
	default:
	}
}

func (r *recordingInvalidator) orgsSnapshot() []uuid.UUID {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]uuid.UUID, len(r.orgs))
	copy(out, r.orgs)
	return out
}

func waitInvalidated(t *testing.T, rec *recordingInvalidator, want uuid.UUID) {
	t.Helper()
	deadline := time.After(2 * time.Second)
	for {
		select {
		case got := <-rec.seen:
			if got == want {
				return
			}
		case <-deadline:
			t.Fatalf("timed out waiting for invalidate of %s; saw %v", want, rec.orgsSnapshot())
		}
	}
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
	if loader.callCount() != 1 {
		t.Fatalf("calls=%d", loader.callCount())
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
		if loader.callCount() >= 2 {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("cache not invalidated within 1s; loader.calls=%d", loader.callCount())
}

func TestSubscriber_StopUnblocksReceive(t *testing.T) {
	client := newMiniRedis(t)
	cache, _ := seedCachedDeny(t, uuid.New())
	sub, err := NewSubscriber(client, cache, logger.Discard("modelpolicy-stop"), NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() {
		sub.Run(context.Background())
		close(done)
	}()
	waitPubSubPatterns(t, client)
	sub.Stop()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Stop did not unblock Run within 2s")
	}
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
