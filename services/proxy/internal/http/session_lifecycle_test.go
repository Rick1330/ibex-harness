package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type memSessionStore struct {
	mu             sync.Mutex
	sessions       map[string]*session.Session
	checkpoints    []session.CheckpointParams
	getErr         error
	appendErr      error
	appendFailOnce error
	getCalls       int
	appendCalls    int
	getDelay       time.Duration
}

func newMemSessionStore() *memSessionStore {
	return &memSessionStore{sessions: map[string]*session.Session{}}
}

func (m *memSessionStore) key(org, agent uuid.UUID, ext string) string {
	return org.String() + "|" + agent.String() + "|" + ext
}

func (m *memSessionStore) GetOrCreate(_ context.Context, p session.GetOrCreateParams) (*session.Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.getCalls++
	if m.getDelay > 0 {
		time.Sleep(m.getDelay)
	}
	if m.getErr != nil {
		return nil, m.getErr
	}
	k := m.key(p.OrgID, p.AgentID, p.ExternalID)
	if s, ok := m.sessions[k]; ok {
		cp := *s
		return &cp, nil
	}
	s := &session.Session{
		ID: uuid.New(), OrgID: p.OrgID, AgentID: p.AgentID,
		ExternalID: &p.ExternalID, Status: session.StatusActive,
		Model: p.Model, Provider: p.Provider, TurnCount: 0,
	}
	m.sessions[k] = s
	cp := *s
	return &cp, nil
}

func (m *memSessionStore) AppendCheckpoint(_ context.Context, p session.CheckpointParams) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.appendCalls++
	if m.appendFailOnce != nil {
		err := m.appendFailOnce
		m.appendFailOnce = nil
		return err
	}
	if m.appendErr != nil {
		return m.appendErr
	}
	m.checkpoints = append(m.checkpoints, p)
	return nil
}

func (m *memSessionStore) Complete(context.Context, uuid.UUID, uuid.UUID) error { return nil }

func (m *memSessionStore) waitAppends(t *testing.T, n int) {
	t.Helper()
	if !waitUntil(2*time.Second, 5*time.Millisecond, func() bool {
		m.mu.Lock()
		defer m.mu.Unlock()
		return m.appendCalls >= n
	}) {
		t.Fatalf("expected >=%d appends", n)
	}
}

func (m *memSessionStore) appendCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.appendCalls
}

func waitUntil(timeout, interval time.Duration, cond func() bool) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return true
		}
		time.Sleep(interval)
	}
	return cond()
}

func neverTrue(timeout, interval time.Duration, cond func() bool) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if cond() {
			return false
		}
		time.Sleep(interval)
	}
	return !cond()
}

func sessionLifecycleRouter(t *testing.T, store session.Store, pool *asyncpool.Pool, cache *sessioncache.Cache) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(stubLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		body: `{"choices":[{"message":{"content":"hello"}}]}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	return NewRouter(RouterDeps{
		Config: chatTestConfig(), Logger: logger.Discard("proxy"),
		Metrics: metrics.NewProxy("test"), Tracer: telemetry.NoopTracer("proxy"),
		Validator: &chatMockValidator{res: &auth.ValidateResult{
			OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
		}},
		AgentVerifier: passAgentVerifier{}, Limiter: ratelimit.Noop(),
		SessionStore: store, SessionCache: cache, CheckpointPool: pool,
		Health:           testHealthServer(),
		ProviderRegistry: reg,
	})
}

func cleanupPool(t *testing.T, pool *asyncpool.Pool) {
	t.Helper()
	t.Cleanup(func() {
		if err := pool.Shutdown(context.Background()); err != nil {
			t.Errorf("shutdown: %v", err)
		}
	})
}

func TestUnit_SessionLifecycle_MintAndReuse(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	pool, err := asyncpool.New(2, 8, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	handler := sessionLifecycleRouter(t, store, pool, nil)

	rec1 := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	if rec1.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec1.Code, rec1.Body.String())
	}
	ext := rec1.Header().Get(headerSessionID)
	if ext == "" {
		t.Fatal("expected minted X-IBEX-Session-ID")
	}
	if _, err := uuid.Parse(ext); err != nil {
		t.Fatalf("external id: %v", err)
	}
	store.waitAppends(t, 1)

	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"gpt-4o","messages":[{"role":"user","content":"again"}]}`))
	req.Header.Set("Authorization", "Bearer t")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", testChatAgentID)
	req.Header.Set(headerSessionID, ext)
	rec2 := httptest.NewRecorder()
	handler.ServeHTTP(rec2, req)
	if rec2.Header().Get(headerSessionID) != ext {
		t.Fatalf("reuse header=%q want %q", rec2.Header().Get(headerSessionID), ext)
	}
	store.waitAppends(t, 2)
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.getCalls < 2 {
		t.Fatalf("getCalls=%d", store.getCalls)
	}
	if len(store.sessions) != 1 {
		t.Fatalf("sessions=%d want 1", len(store.sessions))
	}
}

func TestUnit_SessionLifecycle_FailOpenKeepsStickyHeader(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	store.getErr = errors.New("db down")
	pool, err := asyncpool.New(1, 4, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	handler := sessionLifecycleRouter(t, store, pool, nil)
	rec := postChat(t, handler, chatRequestOpts{
		body: `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`,
		auth: true, agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	if rec.Header().Get(headerSessionID) == "" {
		t.Fatal("expected sticky session header on fail-open")
	}
	if !neverTrue(80*time.Millisecond, 5*time.Millisecond, func() bool {
		return store.appendCount() > 0
	}) {
		t.Fatalf("appendCalls=%d", store.appendCount())
	}
}

func TestUnit_SessionLifecycle_StreamSetsHeaderBeforeBody(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	pool, err := asyncpool.New(1, 4, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)

	reg, err := provider.NewRegistry(&streamStubProvider{
		name: "openai", models: []string{"gpt-4o"},
		chunks: []string{
			"data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\n",
			"data: [DONE]\n\n",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	handler := NewRouter(RouterDeps{
		Config: chatTestConfig(), Logger: logger.Discard("proxy"),
		Metrics: metrics.NewProxy("test"), Tracer: telemetry.NoopTracer("proxy"),
		Validator: &chatMockValidator{res: &auth.ValidateResult{
			OrgID: testChatOrgID, Permissions: permissions.ProxyChatCompletion,
		}},
		AgentVerifier: passAgentVerifier{}, Limiter: ratelimit.Noop(),
		SessionStore: store, CheckpointPool: pool,
		Health: testHealthServer(), ProviderRegistry: reg,
	})
	rec := postChat(t, handler, chatRequestOpts{
		body:    `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:    true,
		agentID: testChatAgentID,
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	if rec.Header().Get(headerSessionID) == "" {
		t.Fatal("expected session header on stream")
	}
	if !strings.Contains(rec.Header().Get("Content-Type"), "text/event-stream") {
		t.Fatalf("ct=%q", rec.Header().Get("Content-Type"))
	}
	store.waitAppends(t, 1)
}

func TestUnit_SessionLifecycle_CacheHitSkipsStore(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	store := newMemSessionStore()
	pool, err := asyncpool.New(1, 4, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)

	org := uuid.MustParse(testChatOrgID)
	agent := uuid.MustParse(testChatAgentID)
	ext := uuid.New().String()
	sid := uuid.New()
	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}, sessioncache.Entry{
		SessionID: sid, TurnCount: 2,
	})

	handler := sessionLifecycleRouter(t, store, pool, cache)
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`))
	req.Header.Set("Authorization", "Bearer t")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", testChatAgentID)
	req.Header.Set(headerSessionID, ext)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Header().Get(headerSessionID) != ext {
		t.Fatalf("header=%q", rec.Header().Get(headerSessionID))
	}
	store.waitAppends(t, 1)
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.getCalls != 0 {
		t.Fatalf("getCalls=%d want 0 (cache hit)", store.getCalls)
	}
	if store.checkpoints[0].SessionID != sid || store.checkpoints[0].TurnIndex != 2 {
		t.Fatalf("cp=%+v", store.checkpoints[0])
	}
}

func TestUnit_SessionLifecycle_CrossOrgUsesTokenOrg(t *testing.T) {
	t.Parallel()
	store := newMemSessionStore()
	pool, err := asyncpool.New(1, 4, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)
	handler := sessionLifecycleRouter(t, store, pool, nil)
	ext := uuid.New().String()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`))
	req.Header.Set("Authorization", "Bearer t")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-IBEX-Agent-ID", testChatAgentID)
	req.Header.Set(headerSessionID, ext)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	store.waitAppends(t, 1)
	store.mu.Lock()
	defer store.mu.Unlock()
	wantOrg := uuid.MustParse(testChatOrgID)
	for _, s := range store.sessions {
		if s.OrgID != wantOrg {
			t.Fatalf("org=%s want %s", s.OrgID, wantOrg)
		}
	}
}

func TestUnit_StickyExternalID(t *testing.T) {
	t.Parallel()
	minted, ok := stickyExternalID("")
	if !ok || minted == "" {
		t.Fatal("expected mint")
	}
	if _, err := uuid.Parse(minted); err != nil {
		t.Fatalf("mint uuid: %v", err)
	}
	got, ok := stickyExternalID("  abc  ")
	if !ok || got != "abc" {
		t.Fatalf("got=%q ok=%v", got, ok)
	}
	tooLong := strings.Repeat("x", maxExternalIDLen+1)
	if _, ok := stickyExternalID(tooLong); ok {
		t.Fatal("expected reject oversized")
	}
}

func TestUnit_ResolveSession_NilStore(t *testing.T) {
	t.Parallel()

	h := chatCompletionHandler{log: logger.Discard("proxy")}
	req := httptest.NewRequest(http.MethodPost, "/", nil)
	parsed := &llm.ChatCompletionRequest{Model: "m"}

	out := h.resolveSessionForRequest(req, parsed, "openai")

	rs, ok := ResolvedSessionFromContext(out.Context())
	if !ok || rs.ExternalID == "" {
		t.Fatal("expected sticky external id without store")
	}
	if rs.durable() {
		t.Fatal("expected non-durable sticky-only session")
	}
}

func TestUnit_CompletionTextFromJSON(t *testing.T) {
	t.Parallel()
	got := completionTextFromJSON([]byte(`{"choices":[{"message":{"content":"hi"}}]}`))
	if got != "hi" {
		t.Fatalf("got=%q", got)
	}
	if completionTextFromJSON([]byte(`{`)) != "" {
		t.Fatal("expected empty on bad json")
	}
}

func TestUnit_BuildCheckpointParams(t *testing.T) {
	t.Parallel()
	rs := resolvedSession{
		SessionID: uuid.New(), ExternalID: "e", TurnIndex: 3,
		OrgID: uuid.New(), AgentID: uuid.New(),
	}
	p := buildCheckpointParams(rs, checkpointInput{
		Messages:       []llm.Message{{Role: "user", Content: "x"}},
		CompletionText: "y", Model: "m", Provider: "p",
		Usage:   &provider.Usage{InputTokens: 1, OutputTokens: 2},
		Latency: 1500 * time.Millisecond, IsStreaming: true, IsComplete: true,
	}, "req-1")
	if p.TurnIndex != 3 {
		t.Fatalf("turn=%d", p.TurnIndex)
	}
	if p.InputTokens != 1 {
		t.Fatalf("in=%d", p.InputTokens)
	}
	if p.OutputTokens != 2 {
		t.Fatalf("out=%d", p.OutputTokens)
	}
	if p.LatencyMs != 1500 {
		t.Fatalf("latency=%d", p.LatencyMs)
	}
	if p.MessagesHash == "" {
		t.Fatal("expected messages hash")
	}
	if p.CompletionHash == "" {
		t.Fatal("expected completion hash")
	}
}

func TestUnit_RunCheckpoint_DuplicateInvalidatesCache(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	store := newMemSessionStore()
	store.appendErr = session.ErrDuplicateTurn
	org, agent := uuid.New(), uuid.New()
	ext := "ext"
	sid := uuid.New()
	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}, sessioncache.Entry{SessionID: sid, TurnCount: 1})
	deps := sessionLifecycleDeps{
		store: store, cache: cache, log: logger.Discard("proxy"),
	}
	deps.runCheckpoint(session.CheckpointParams{
		SessionID: sid, OrgID: org, AgentID: agent, TurnIndex: 1,
	}, ext)
	if _, ok := cache.Get(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}); ok {
		t.Fatal("expected invalidate")
	}
}

func TestUnit_RunCheckpoint_RetrySucceeds(t *testing.T) {
	t.Parallel()

	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	cache, err := sessioncache.New(client, time.Minute)
	if err != nil {
		t.Fatal(err)
	}

	store := newMemSessionStore()
	store.appendFailOnce = session.ErrDuplicateTurn
	org, agent := uuid.New(), uuid.New()
	ext := "retry-ext"
	sid := uuid.New()
	cache.Set(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	}, sessioncache.Entry{SessionID: sid, TurnCount: 1})

	deps := sessionLifecycleDeps{
		store: store, cache: cache, log: logger.Discard("proxy"),
	}
	deps.runCheckpoint(session.CheckpointParams{
		SessionID: sid, OrgID: org, AgentID: agent, TurnIndex: 0,
		Model: "m", Provider: "p",
	}, ext)

	if store.appendCount() < 2 {
		t.Fatalf("appendCalls=%d want >=2", store.appendCount())
	}
	got, ok := cache.Get(context.Background(), sessioncache.LookupKey{
		OrgID: org, AgentID: agent, ExternalID: ext,
	})
	if !ok {
		t.Fatal("expected cache refresh after retry")
	}
	if got.TurnCount < 1 {
		t.Fatalf("turn_count=%d", got.TurnCount)
	}
}

func TestUnit_ReadLimitedBody(t *testing.T) {
	t.Parallel()

	ok, err := readLimitedBody(strings.NewReader("abc"), 3)
	if err != nil || string(ok) != "abc" {
		t.Fatalf("ok=%q err=%v", ok, err)
	}

	_, err = readLimitedBody(strings.NewReader("abcd"), 3)
	if !errors.Is(err, errProviderResponseTooLarge) {
		t.Fatalf("err=%v", err)
	}
}

func TestUnit_EnqueueCheckpoint_SkipsStickyOnly(t *testing.T) {
	t.Parallel()

	store := newMemSessionStore()
	pool, err := asyncpool.New(1, 2, nil)
	if err != nil {
		t.Fatal(err)
	}
	cleanupPool(t, pool)

	h := chatCompletionHandler{
		sessionStore: store, checkpointPool: pool, log: logger.Discard("proxy"),
	}
	ctx := withResolvedSession(context.Background(), resolvedSession{ExternalID: "sticky"})
	h.enqueueCheckpoint(ctx, checkpointInput{CompletionText: "x", Model: "m", Provider: "p"})

	if !neverTrue(50*time.Millisecond, 5*time.Millisecond, func() bool {
		return store.appendCount() > 0
	}) {
		t.Fatal("expected no checkpoint for sticky-only session")
	}
}
