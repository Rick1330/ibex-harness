package session

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/google/uuid"
)

func TestUnit_Resolved_Durable(t *testing.T) {
	t.Parallel()
	durable := Resolved{SessionID: uuid.New()}
	if !durable.Durable() {
		t.Fatal("expected durable")
	}
	sticky := Resolved{ExternalID: "sticky"}
	if sticky.Durable() {
		t.Fatal("sticky-only is not durable")
	}
}

func TestUnit_Resolve_NilStore(t *testing.T) {
	t.Parallel()
	deps := LifecycleDeps{Log: logger.Discard("t")}
	out, err := deps.Resolve(context.Background(), ResolveInput{
		ExternalID: "ext", OrgID: uuid.New(), AgentID: uuid.New(),
	})
	if err != nil {
		t.Fatal(err)
	}
	if out != nil {
		t.Fatalf("got=%+v", out)
	}
}

func TestUnit_Resolve_NilTenant(t *testing.T) {
	t.Parallel()
	deps := LifecycleDeps{Store: newMemSessionStore(), Log: logger.Discard("t")}
	out, err := deps.Resolve(context.Background(), ResolveInput{ExternalID: "ext"})
	if err != nil {
		t.Fatal(err)
	}
	if out != nil {
		t.Fatalf("got=%+v", out)
	}
}

func TestUnit_Resolve_GetOrCreate(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	deps := LifecycleDeps{Store: store, Log: logger.Discard("t")}
	org, agent := uuid.New(), uuid.New()
	ext := uuid.New().String()

	out, err := deps.Resolve(context.Background(), ResolveInput{
		ExternalID: ext, OrgID: org, AgentID: agent,
		Parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"}, ProviderName: "openai",
	})
	if err != nil {
		t.Fatal(err)
	}
	if out == nil {
		t.Fatal("expected resolved session")
	}
	if out.SessionID == uuid.Nil {
		t.Fatal("expected durable session id")
	}
	if out.ExternalID != ext {
		t.Fatalf("external=%q", out.ExternalID)
	}
	store.mu.Lock()
	getCalls := store.getCalls
	store.mu.Unlock()
	if getCalls != 1 {
		t.Fatalf("getCalls=%d", getCalls)
	}
}

func TestUnit_Resolve_GetOrCreateError(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	store.getErr = errors.New("db down")
	deps := LifecycleDeps{Store: store, Log: logger.Discard("t")}
	_, err := deps.Resolve(context.Background(), ResolveInput{
		ExternalID: "ext", OrgID: uuid.New(), AgentID: uuid.New(),
		Parsed: &llm.ChatCompletionRequest{Model: "m"}, ProviderName: "openai",
	})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestUnit_Resolve_CacheHitSkipsStore(t *testing.T) {
	t.Parallel()
	cache := newTestCache(t)
	store := newMemSessionStore()
	deps := LifecycleDeps{Store: store, Cache: cache, Log: logger.Discard("t")}

	org, agent := uuid.New(), uuid.New()
	ext := uuid.New().String()
	sid := uuid.New()
	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}, sessioncache.Entry{SessionID: sid, TurnCount: 2})

	out, err := deps.Resolve(context.Background(), ResolveInput{
		ExternalID: ext, OrgID: org, AgentID: agent,
		Parsed: &llm.ChatCompletionRequest{Model: "gpt-4o"}, ProviderName: "openai",
	})
	if err != nil {
		t.Fatal(err)
	}
	if out.SessionID != sid {
		t.Fatalf("session=%s", out.SessionID)
	}
	if out.TurnIndex != 2 {
		t.Fatalf("turn=%d", out.TurnIndex)
	}
	store.mu.Lock()
	getCalls := store.getCalls
	store.mu.Unlock()
	if getCalls != 0 {
		t.Fatalf("getCalls=%d want 0", getCalls)
	}
}

func TestUnit_GetOrCreateTimeout_Default(t *testing.T) {
	t.Parallel()
	deps := LifecycleDeps{}
	if deps.getOrCreateTimeout() != defaultGetOrCreateTO {
		t.Fatalf("timeout=%v", deps.getOrCreateTimeout())
	}
	deps.GetOrCreateTO = 2 * time.Second
	if deps.getOrCreateTimeout() != 2*time.Second {
		t.Fatalf("timeout=%v", deps.getOrCreateTimeout())
	}
}
