package ratelimit

import (
	"context"
	"database/sql"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"

	_ "github.com/lib/pq"
)

func TestUnit_ConfigUpdateEvent_validationErrors(t *testing.T) {
	t.Parallel()
	cases := []ConfigUpdateEvent{
		{Version: 2, OrgID: uuid.New().String()},
		{Version: ConfigEventVersion, OrgID: ""},
		{Version: ConfigEventVersion, OrgID: "not-a-uuid"},
	}
	for _, e := range cases {
		if _, err := e.Marshal(); err == nil {
			t.Fatalf("expected marshal error for %+v", e)
		}
	}
	if _, err := ParseConfigUpdateEvent("{"); err == nil {
		t.Fatal("expected parse error")
	}
	if _, err := ParseConfigUpdateEvent(`{"v":1,"org_id":"bad"}`); err == nil {
		t.Fatal("expected validate error")
	}
}

func TestUnit_OrgIDFromChannel_rejectsBad(t *testing.T) {
	t.Parallel()
	if _, err := OrgIDFromChannel("other:x"); err == nil {
		t.Fatal("expected error")
	}
	if _, err := OrgIDFromChannel(ChannelPrefix); err == nil {
		t.Fatal("expected error for empty org")
	}
}

func TestUnit_NewConfigPublisher_validation(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	log := logger.Discard("ratelimit-test")
	if _, err := NewConfigPublisher(nil, log); err == nil {
		t.Fatal("nil client")
	}
	if _, err := NewConfigPublisher(client, nil); err == nil {
		t.Fatal("nil log")
	}
	if err := (NoopConfigPublisher{}).Publish(context.Background(), ConfigUpdateEvent{}); err != nil {
		t.Fatal(err)
	}
}

func TestUnit_ConfigPublisher_PublishInvalidEvent(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	pub, err := NewConfigPublisher(client, logger.Discard("ratelimit-test"))
	if err != nil {
		t.Fatal(err)
	}
	if err := pub.Publish(context.Background(), ConfigUpdateEvent{Version: 1, OrgID: "bad"}); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_NewConfigStore_nil(t *testing.T) {
	t.Parallel()
	if _, err := NewConfigStore(nil); err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_ConfigStore_LoadFailsWithoutPostgres(t *testing.T) {
	t.Parallel()
	db, err := sql.Open("postgres", "postgres://127.0.0.1:1/nope?sslmode=disable&connect_timeout=1")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewConfigStore(db)
	if err != nil {
		t.Fatal(err)
	}
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440310")
	if _, err := store.LoadOrg(context.Background(), org); err == nil {
		t.Fatal("expected LoadOrg error")
	}
	if _, err := store.LoadAll(context.Background()); err == nil {
		t.Fatal("expected LoadAll error")
	}
}

func TestUnit_NewConfigSubscriber_validation(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	log := logger.Discard("ratelimit-test")
	store := &memOverrideLoader{}
	lim := newTestHierarchical(t, HierarchicalConfig{DefaultRPM: 60, GlobalRPM: 1000})
	hier, _ := AsHierarchical(lim)
	if _, err := NewConfigSubscriber(nil, store, hier, log, 0); err == nil {
		t.Fatal("nil client")
	}
	if _, err := NewConfigSubscriber(client, nil, hier, log, 0); err == nil {
		t.Fatal("nil store")
	}
	if _, err := NewConfigSubscriber(client, store, nil, log, 0); err == nil {
		t.Fatal("nil applier")
	}
	if _, err := NewConfigSubscriber(client, store, hier, nil, 0); err == nil {
		t.Fatal("nil log")
	}
	sub, err := NewConfigSubscriber(client, store, hier, log, 0)
	if err != nil {
		t.Fatal(err)
	}
	if sub.pollEvery != DefaultConfigPollInterval {
		t.Fatalf("pollEvery=%v", sub.pollEvery)
	}
	sub.Stop()
}

func TestConfigSubscriber_pubsubAppliesWithinOneSecond(t *testing.T) {
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440320")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440420")
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	limIface, err := NewHierarchicalLimiter(client, HierarchicalConfig{
		DefaultRPM: 100, GlobalRPM: 10_000,
	})
	if err != nil {
		t.Fatal(err)
	}
	lim, _ := AsHierarchical(limIface)
	rpm := int64(2)
	loader := &memOverrideLoader{byOrg: map[uuid.UUID]OrgOverrideSet{
		org: {OrgRPM: &rpm},
	}}
	sub, err := NewConfigSubscriber(client, loader, lim, logger.Discard("rl"), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)
	t.Cleanup(func() {
		sub.Stop()
		cancel()
		<-sub.Done()
	})
	// Wait until PSUBSCRIBE is ready.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		n, err := client.PubSubNumPat(context.Background()).Result()
		if err == nil && n > 0 {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	start := time.Now()
	pub, err := NewConfigPublisher(client, logger.Discard("rl"))
	if err != nil {
		t.Fatal(err)
	}
	if err := pub.Publish(context.Background(), ConfigUpdateEvent{
		Version: ConfigEventVersion, OrgID: org.String(),
	}); err != nil {
		t.Fatal(err)
	}
	var applied bool
	for time.Since(start) < time.Second {
		orgLim, _, _ := lim.resolvedLimits(org, agent)
		if orgLim == 2 {
			applied = true
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	elapsed := time.Since(start)
	t.Logf("pubsub override propagation latency: %s", elapsed)
	if !applied {
		t.Fatalf("override not applied within 1s (elapsed=%s)", elapsed)
	}
	assertCheckWant(t, checkArgs{lim: lim, org: org, agent: agent}, true)
	assertCheckWant(t, checkArgs{lim: lim, org: org, agent: agent}, true)
	res := assertCheckWant(t, checkArgs{lim: lim, org: org, agent: agent}, false)
	if res.DeniedTier != tierOrg {
		t.Fatalf("DeniedTier=%q", res.DeniedTier)
	}
}

func TestConfigSubscriber_pollMissConverges(t *testing.T) {
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440321")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440421")
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	limIface, err := NewHierarchicalLimiter(client, HierarchicalConfig{
		DefaultRPM: 100, GlobalRPM: 10_000,
	})
	if err != nil {
		t.Fatal(err)
	}
	lim, _ := AsHierarchical(limIface)
	loader := &memOverrideLoader{byOrg: map[uuid.UUID]OrgOverrideSet{}}
	pollEvery := 50 * time.Millisecond
	sub, err := NewConfigSubscriber(client, loader, lim, logger.Discard("rl"), pollEvery)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sub.Run(ctx)
	t.Cleanup(func() {
		sub.Stop()
		cancel()
		<-sub.Done()
	})
	// Simulate PATCH without PUBLISH: mutate store only.
	rpm := int64(1)
	start := time.Now()
	loader.set(org, OrgOverrideSet{OrgRPM: &rpm})
	var applied bool
	for time.Since(start) < 2*time.Second {
		orgLim, _, _ := lim.resolvedLimits(org, agent)
		if orgLim == 1 {
			applied = true
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	elapsed := time.Since(start)
	t.Logf("poll-miss override propagation latency: %s (pollEvery=%s)", elapsed, pollEvery)
	if !applied {
		t.Fatalf("poll did not apply override (elapsed=%s)", elapsed)
	}
	if elapsed > 30*time.Second {
		t.Fatalf("poll latency %s exceeds 30s budget", elapsed)
	}
}

func TestConfigSubscriber_handleMessage_malformedAndMismatch(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	lim, _ := AsHierarchical(newTestHierarchical(t, HierarchicalConfig{DefaultRPM: 10, GlobalRPM: 100}))
	loader := &memOverrideLoader{err: errors.New("db down")}
	sub, err := NewConfigSubscriber(client, loader, lim, logger.Discard("rl"), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440322")
	other := uuid.MustParse("550e8400-e29b-41d4-a716-446655440323")
	sub.handleMessage(context.Background(), ChannelForOrg(org), "{")
	payload, _ := (ConfigUpdateEvent{Version: ConfigEventVersion, OrgID: other.String()}).Marshal()
	sub.handleMessage(context.Background(), ChannelForOrg(org), string(payload))
	okPayload, _ := (ConfigUpdateEvent{Version: ConfigEventVersion, OrgID: org.String()}).Marshal()
	sub.handleMessage(context.Background(), ChannelForOrg(org), string(okPayload)) // load err kept
	sub.pollOnce(context.Background())                                             // load all err kept
}

func TestHierarchical_OrgRPMRedisKey_andDBWinsOverEnv(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440324")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440424")
	limIface := newTestHierarchical(t, HierarchicalConfig{
		DefaultRPM:   60,
		OrgOverrides: map[uuid.UUID]int64{org: 200},
		GlobalRPM:    10_000,
	})
	lim, _ := AsHierarchical(limIface)
	orgLim, _, _ := lim.resolvedLimits(org, agent)
	if orgLim != 200 {
		t.Fatalf("env org=%d", orgLim)
	}
	dbRPM := int64(5)
	lim.ApplyOrgOverrides(org, OrgOverrideSet{OrgRPM: &dbRPM, AgentRPM: map[uuid.UUID]int64{agent: 3}})
	orgLim, agentLim, _ := lim.resolvedLimits(org, agent)
	if orgLim != 5 || agentLim != 3 {
		t.Fatalf("db wins org=%d agent=%d", orgLim, agentLim)
	}
	key := OrgRPMRedisKey(org)
	if key == "" || key[:len("ratelimit:")] != "ratelimit:" {
		t.Fatalf("key=%q", key)
	}
	lim.ReplaceAllOverrides(map[uuid.UUID]OrgOverrideSet{
		org: {AgentRPM: map[uuid.UUID]int64{agent: 7}},
	})
	orgLim, agentLim, _ = lim.resolvedLimits(org, agent)
	if orgLim != 200 || agentLim != 7 {
		t.Fatalf("after replace org=%d agent=%d want env org 200 agent 7", orgLim, agentLim)
	}
}

func TestUnit_buildOverrideSets(t *testing.T) {
	t.Parallel()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440330")
	agent := uuid.MustParse("550e8400-e29b-41d4-a716-446655440430")
	got, err := buildOverrideSets([]overrideScan{
		{OrgID: org, AgentNull: sql.NullString{}, RPM: 90},
		{OrgID: org, AgentNull: sql.NullString{String: agent.String(), Valid: true}, RPM: 12},
	})
	if err != nil {
		t.Fatal(err)
	}
	if got[org].OrgRPM == nil || *got[org].OrgRPM != 90 {
		t.Fatalf("org rpm: %+v", got[org].OrgRPM)
	}
	if got[org].AgentRPM[agent] != 12 {
		t.Fatalf("agent rpm: %+v", got[org].AgentRPM)
	}
	if _, err := buildOverrideSets([]overrideScan{
		{OrgID: org, AgentNull: sql.NullString{String: "bad", Valid: true}, RPM: 1},
	}); err == nil {
		t.Fatal("expected bad agent id")
	}
}

func TestUnit_ConfigPublisher_PublishRedisError(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	pub, err := NewConfigPublisher(client, logger.Discard("rl"))
	if err != nil {
		t.Fatal(err)
	}
	_ = client.Close()
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440331")
	if err := pub.Publish(context.Background(), ConfigUpdateEvent{
		Version: ConfigEventVersion, OrgID: org.String(),
	}); err == nil {
		t.Fatal("expected publish error")
	}
}

type memOverrideLoader struct {
	mu    sync.Mutex
	byOrg map[uuid.UUID]OrgOverrideSet
	err   error
}

func (m *memOverrideLoader) set(org uuid.UUID, set OrgOverrideSet) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.byOrg == nil {
		m.byOrg = map[uuid.UUID]OrgOverrideSet{}
	}
	m.byOrg[org] = set
}

func (m *memOverrideLoader) LoadOrg(_ context.Context, orgID uuid.UUID) (OrgOverrideSet, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.err != nil {
		return OrgOverrideSet{}, m.err
	}
	return m.byOrg[orgID], nil
}

func (m *memOverrideLoader) LoadAll(context.Context) (map[uuid.UUID]OrgOverrideSet, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.err != nil {
		return nil, m.err
	}
	out := make(map[uuid.UUID]OrgOverrideSet, len(m.byOrg))
	for k, v := range m.byOrg {
		out[k] = v
	}
	return out, nil
}
