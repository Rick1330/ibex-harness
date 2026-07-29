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
	"github.com/google/uuid"
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

	assertAppendCount(t, fx, 1)
	assertCacheTurnCount(t, fx, 1)
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

	assertMinAppendCount(t, fx, 2)
	assertCacheTurnAtLeast(t, fx, 1)
}

func TestUnit_RunCheckpoint_AppendError(t *testing.T) {
	t.Parallel()

	fx := newCheckpointFixture(t)
	fx.store.appendErr = errors.New("db down")

	fx.deps.RunCheckpoint(fx.params(0), fx.ext)

	assertAppendCount(t, fx, 1)
}

func assertAppendCount(t *testing.T, fx checkpointFixture, want int) {
	t.Helper()
	if fx.store.appendCount() != want {
		t.Fatalf("appends=%d want %d", fx.store.appendCount(), want)
	}
}

func assertMinAppendCount(t *testing.T, fx checkpointFixture, want int) {
	t.Helper()
	if fx.store.appendCount() < want {
		t.Fatalf("appendCalls=%d want >=%d", fx.store.appendCount(), want)
	}
}

func assertCacheTurnCount(t *testing.T, fx checkpointFixture, want int) {
	t.Helper()
	got, ok := fx.cache.Get(context.Background(), fx.key())
	if !ok {
		t.Fatal("expected cache hit")
	}
	if got.TurnCount != want {
		t.Fatalf("turnCount=%d want %d", got.TurnCount, want)
	}
}

func assertCacheTurnAtLeast(t *testing.T, fx checkpointFixture, want int) {
	t.Helper()
	got, ok := fx.cache.Get(context.Background(), fx.key())
	if !ok {
		t.Fatal("expected cache hit")
	}
	if got.TurnCount < want {
		t.Fatalf("turnCount=%d want >=%d", got.TurnCount, want)
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
	cache := newTestCache(t)
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
