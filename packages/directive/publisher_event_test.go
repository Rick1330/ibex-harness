package directive_test

import (
	"context"
	"database/sql"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"

	// Register the lib/pq "postgres" driver for sql.Open in unit tests.
	_ "github.com/lib/pq"
)

func TestUnit_UpdateEventValidateAndParse(t *testing.T) {
	t.Parallel()
	orgID := uuid.New().String()
	agentID := uuid.New().String()
	valid := directive.UpdateEvent{Version: 1, OrgID: orgID, AgentID: agentID}
	raw, err := valid.Marshal()
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	parsed, err := directive.ParseUpdateEvent(string(raw))
	if err != nil || parsed.OrgID != orgID {
		t.Fatalf("parse: %+v err=%v", parsed, err)
	}

	cases := []directive.UpdateEvent{
		{Version: 2, OrgID: orgID, AgentID: agentID},
		{Version: 1, OrgID: "", AgentID: agentID},
		{Version: 1, OrgID: orgID, AgentID: ""},
		{Version: 1, OrgID: "not-uuid", AgentID: agentID},
		{Version: 1, OrgID: orgID, AgentID: "not-uuid"},
	}
	for _, ev := range cases {
		if err := ev.Validate(); err == nil {
			t.Fatalf("expected validate error for %+v", ev)
		}
	}
	if _, err := directive.ParseUpdateEvent("{"); err == nil {
		t.Fatal("expected decode error")
	}
}

func TestUnit_PublisherValidationAndNoop(t *testing.T) {
	t.Parallel()
	log := mustLogger(t)
	if _, err := directive.NewRedisPublisher(nil, log); err == nil {
		t.Fatal("expected nil client error")
	}
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	if _, err := directive.NewRedisPublisher(client, nil); err == nil {
		t.Fatal("expected nil logger error")
	}
	pub, err := directive.NewRedisPublisher(client, log)
	if err != nil {
		t.Fatalf("publisher: %v", err)
	}
	bad := directive.UpdateEvent{Version: 1, OrgID: "bad", AgentID: uuid.New().String()}
	if err := pub.Publish(context.Background(), bad); err == nil {
		t.Fatal("expected publish validation error")
	}
	if err := (directive.NoopPublisher{}).Publish(context.Background(), bad); err != nil {
		t.Fatalf("noop: %v", err)
	}
	orgID := uuid.New()
	agentID := uuid.New()
	if err := pub.Publish(context.Background(), directive.UpdateEvent{
		Version: 1, OrgID: orgID.String(), AgentID: agentID.String(),
	}); err != nil {
		t.Fatalf("publish: %v", err)
	}
}

func TestUnit_PublisherClosedRedis(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	pub, err := directive.NewRedisPublisher(client, mustLogger(t))
	if err != nil {
		t.Fatalf("publisher: %v", err)
	}
	mr.Close()
	err = pub.Publish(context.Background(), directive.UpdateEvent{
		Version: 1, OrgID: uuid.New().String(), AgentID: uuid.New().String(),
	})
	assertPublishErr(t, err)
}

func TestUnit_NewSubscriberValidation(t *testing.T) {
	t.Parallel()
	log := mustLogger(t)
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache := directive.NoopResolver{}
	if _, err := directive.NewSubscriber(nil, cache, log, nil); err == nil {
		t.Fatal("expected nil client")
	}
	if _, err := directive.NewSubscriber(client, nil, log, nil); err == nil {
		t.Fatal("expected nil cache")
	}
	if _, err := directive.NewSubscriber(client, cache, nil, nil); err == nil {
		t.Fatal("expected nil logger")
	}
	sub, err := directive.NewSubscriber(client, cache, log, nil)
	if err != nil {
		t.Fatalf("subscriber: %v", err)
	}
	sub.Stop()
}

func TestUnit_SubscriberStopWithoutRun(t *testing.T) {
	t.Parallel()
	log := mustLogger(t)
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	sub, err := directive.NewSubscriber(client, directive.NoopResolver{}, log, nil)
	if err != nil {
		t.Fatalf("subscriber: %v", err)
	}
	// Stop before Run must not block waiting on Done.
	done := make(chan struct{})
	go func() {
		sub.Stop()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("Stop blocked without Run")
	}
}

func TestUnit_SubscriberIgnoresMalformedEvents(t *testing.T) {
	t.Parallel()
	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{Content: "v1", InjectionMode: "system_first"})
	mr, client := newTestRedis(t)
	log := mustLogger(t)
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: log,
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	_, _ = r.Resolve(context.Background(), orgID, agentID)
	waitRedisDirective(t, client, orgID, agentID)
	sub, err := directive.NewSubscriber(client, r, log, nil)
	if err != nil {
		t.Fatalf("subscriber: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)
	waitSubscribed(t, mr)

	channel := directive.ChannelForOrg(orgID)
	_ = client.Publish(ctx, channel, "{").Err()
	_ = client.Publish(ctx, channel, `{"v":1,"org_id":"not-uuid","agent_id":"`+agentID.String()+`"}`).Err()
	otherOrg := uuid.New()
	_ = client.Publish(ctx, channel, `{"v":1,"org_id":"`+otherOrg.String()+`","agent_id":"`+agentID.String()+`"}`).Err()

	got, err := r.Resolve(context.Background(), orgID, agentID)
	assertResolveOK(t, got, err, "v1")
	assertStoreLoads(t, store, 1)
	sub.Stop()
	cancel()
	<-sub.Done()
}

func TestUnit_PostgresStoreNilDB(t *testing.T) {
	t.Parallel()
	if _, err := directive.NewPostgresStore(nil); err == nil {
		t.Fatal("expected nil db error")
	}
}

func TestUnit_PostgresStoreLoadBeginFails(t *testing.T) {
	t.Parallel()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/nope?sslmode=disable&connect_timeout=1")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := directive.NewPostgresStore(db)
	if err != nil {
		t.Fatalf("store: %v", err)
	}
	_, err = store.Load(context.Background(), uuid.New(), uuid.New())
	if err == nil {
		t.Fatal("expected begin/connect error")
	}
}

func TestUnit_CorruptCacheTreatedAsMiss(t *testing.T) {
	t.Parallel()
	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{Content: "ok", InjectionMode: "system_first"})
	_, client := newTestRedis(t)
	key := orgID.String() + ":directive:" + agentID.String()
	if err := client.Set(context.Background(), key, "{", time.Minute).Err(); err != nil {
		t.Fatalf("seed corrupt: %v", err)
	}
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: mustLogger(t),
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	got, err := r.Resolve(context.Background(), orgID, agentID)
	assertResolveOK(t, got, err, "ok")
	assertStoreLoads(t, store, 1)
}

func TestUnit_PopulateCacheSetFailure(t *testing.T) {
	t.Parallel()
	orgID := uuid.New()
	agentID := uuid.New()
	store := newFakeStore(directive.Resolved{Content: "x", InjectionMode: "system_first"})
	mr, client := newTestRedis(t)
	r, err := directive.NewCachedResolver(directive.CachedResolverDeps{
		Client: client, Loader: store, Config: directive.Config{CacheTTL: time.Minute}, Log: mustLogger(t),
	})
	if err != nil {
		t.Fatalf("resolver: %v", err)
	}
	mr.Close()
	got, err := r.Resolve(context.Background(), orgID, agentID)
	assertResolveOK(t, got, err, "x")
	r.Invalidate(context.Background(), orgID, agentID)
}

func assertResolveOK(t *testing.T, got directive.Resolved, err error, want string) {
	t.Helper()
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if got.Content != want {
		t.Fatalf("content=%q want %q", got.Content, want)
	}
}

func assertStoreLoads(t *testing.T, store *fakeStore, want int) {
	t.Helper()
	if store.loads != want {
		t.Fatalf("loads=%d want %d", store.loads, want)
	}
}

func assertPublishErr(t *testing.T, err error) {
	t.Helper()
	if err == nil {
		t.Fatal("expected publish error")
	}
	if !strings.Contains(err.Error(), "publish") {
		t.Fatalf("want publish error, got %v", err)
	}
}
