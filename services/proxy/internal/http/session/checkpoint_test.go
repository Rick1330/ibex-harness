package session

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	pkgsession "github.com/Rick1330/ibex-harness/packages/session"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

func TestUnit_WantCheckpoint(t *testing.T) {
	t.Parallel()

	durable := Resolved{SessionID: uuid.New(), ExternalID: "e"}
	sticky := Resolved{ExternalID: "sticky"}
	deps := LifecycleDeps{Store: newMemSessionStore()}
	complete := httptrace.RequestOutcome{StatusCode: 200, IsComplete: true}
	failure := httptrace.RequestOutcome{StatusCode: 502, IsComplete: false}
	streamIn := CheckpointInput{IsStreaming: true, IsComplete: false}

	tests := []struct {
		name    string
		deps    LifecycleDeps
		rs      Resolved
		in      CheckpointInput
		outcome httptrace.RequestOutcome
		want    bool
	}{
		{name: "nil store", deps: LifecycleDeps{}, rs: durable, outcome: complete, want: false},
		{name: "sticky only", deps: deps, rs: sticky, outcome: complete, want: false},
		{name: "complete durable", deps: deps, rs: durable, outcome: complete, want: true},
		{name: "streaming incomplete", deps: deps, rs: durable, in: streamIn, outcome: failure, want: true},
		{name: "failure non-stream", deps: deps, rs: durable, outcome: failure, want: false},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := WantCheckpoint(tc.deps, tc.rs, tc.in, tc.outcome)
			if got != tc.want {
				t.Fatalf("got=%v want=%v", got, tc.want)
			}
		})
	}
}

func TestUnit_BuildCheckpointParams(t *testing.T) {
	t.Parallel()
	rs := Resolved{
		SessionID: uuid.New(), ExternalID: "e", TurnIndex: 3,
		OrgID: uuid.New(), AgentID: uuid.New(),
	}
	p := BuildCheckpointParams(rs, CheckpointInput{
		Messages:       []llm.Message{{Role: "user", Content: "x"}},
		CompletionText: "y", Model: "m", Provider: "p",
		Usage:       &provider.Usage{InputTokens: 1, OutputTokens: 2},
		Latency:     1500 * time.Millisecond,
		IsStreaming: true, IsComplete: true, ProviderReqID: "prov-req",
	}, "req-1")
	if p.TurnIndex != 3 {
		t.Fatalf("turn=%d", p.TurnIndex)
	}
	if p.InputTokens != 1 || p.OutputTokens != 2 {
		t.Fatalf("tokens in=%d out=%d", p.InputTokens, p.OutputTokens)
	}
	if p.LatencyMs != 1500 {
		t.Fatalf("latency=%d", p.LatencyMs)
	}
	if p.MessagesHash == "" || p.CompletionHash == "" {
		t.Fatal("expected hashes")
	}
	if p.ProviderRequestID != "prov-req" {
		t.Fatalf("provider_req=%q", p.ProviderRequestID)
	}
}

func TestUnit_RunCheckpoint_Success(t *testing.T) {
	t.Parallel()
	fx := newCheckpointFixture(t)
	fx.deps.RunCheckpoint(fx.params(0), fx.ext)
	if fx.store.appendCount() != 1 {
		t.Fatalf("appends=%d", fx.store.appendCount())
	}
	got, ok := fx.cache.Get(context.Background(), fx.key())
	if !ok || got.TurnCount != 1 {
		t.Fatalf("cache=%+v ok=%v", got, ok)
	}
}

func TestUnit_RunCheckpoint_DuplicateInvalidatesCache(t *testing.T) {
	t.Parallel()
	fx := newCheckpointFixture(t)
	fx.store.appendErr = pkgsession.ErrDuplicateTurn
	fx.seedCache(1)
	fx.deps.RunCheckpoint(fx.params(1), fx.ext)
	if _, ok := fx.cache.Get(context.Background(), fx.key()); ok {
		t.Fatal("expected invalidate")
	}
}

func TestUnit_RunCheckpoint_RetrySucceeds(t *testing.T) {
	t.Parallel()
	fx := newCheckpointFixture(t)
	fx.store.appendFailOnce = pkgsession.ErrDuplicateTurn
	fx.seedCache(1)
	fx.deps.RunCheckpoint(fx.params(0), fx.ext)
	if fx.store.appendCount() < 2 {
		t.Fatalf("appendCalls=%d want >=2", fx.store.appendCount())
	}
	got, ok := fx.cache.Get(context.Background(), fx.key())
	if !ok || got.TurnCount < 1 {
		t.Fatalf("cache=%+v ok=%v", got, ok)
	}
}

func TestUnit_RunCheckpoint_AppendError(t *testing.T) {
	t.Parallel()
	fx := newCheckpointFixture(t)
	fx.store.appendErr = errors.New("db down")
	fx.deps.RunCheckpoint(fx.params(0), fx.ext)
	if fx.store.appendCount() != 1 {
		t.Fatalf("appends=%d", fx.store.appendCount())
	}
}

type checkpointFixture struct {
	store *memSessionStore
	cache *sessioncache.Cache
	org   uuid.UUID
	agent uuid.UUID
	ext   string
	sid   uuid.UUID
	deps  LifecycleDeps
}

func newCheckpointFixture(t *testing.T) checkpointFixture {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	store := newMemSessionStore()
	org, agent := uuid.New(), uuid.New()
	return checkpointFixture{
		store: store, cache: cache, org: org, agent: agent,
		ext: "ext-" + uuid.New().String()[:8], sid: uuid.New(),
		deps: LifecycleDeps{Store: store, Cache: cache, Log: logger.Discard("proxy")},
	}
}

func (fx checkpointFixture) key() sessioncache.LookupKey {
	return sessioncache.LookupKey{
		OrgID: fx.org, AgentID: fx.agent, ExternalID: fx.ext,
	}
}

func (fx checkpointFixture) seedCache(turnCount int) {
	fx.cache.Set(context.Background(), fx.key(), sessioncache.Entry{
		SessionID: fx.sid, TurnCount: turnCount,
	})
}

func (fx checkpointFixture) params(turnIndex int) pkgsession.CheckpointParams {
	return pkgsession.CheckpointParams{
		SessionID: fx.sid, OrgID: fx.org, AgentID: fx.agent, TurnIndex: turnIndex,
		Model: "m", Provider: "p",
	}
}
