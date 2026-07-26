package http

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
	"unicode/utf8"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/packages/telemetry"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

type countingLLMProvider struct {
	name    string
	models  []string
	body    string
	calls   atomic.Int64
	blockCh chan struct{} // optional: hold Complete until closed
}

func (s *countingLLMProvider) Complete(ctx context.Context, _ provider.Request) (provider.Response, error) {
	s.calls.Add(1)
	if s.blockCh != nil {
		select {
		case <-s.blockCh:
		case <-ctx.Done():
			return provider.Response{}, ctx.Err()
		}
	}
	body := s.body
	if body == "" {
		body = `{"choices":[{"message":{"role":"assistant","content":"ok"}}]}`
	}
	return provider.Response{
		StatusCode: http.StatusOK,
		Body:       io.NopCloser(strings.NewReader(body)),
	}, nil
}

func (s *countingLLMProvider) Name() string              { return s.name }
func (s *countingLLMProvider) SupportedModels() []string { return s.models }

func idempotencyTestRouter(t *testing.T, store idempotency.Store, prov provider.Provider, validator auth.TokenValidator) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(prov)
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	if validator == nil {
		validator = defaultChatValidator()
	}
	cfg := chatTestConfig()
	cfg.IdempotencyTTL = time.Hour
	cfg.IdempotencyRedisTimeout = time.Second
	return NewRouter(RouterDeps{
		Config:           cfg,
		Logger:           logger.Discard("proxy"),
		Metrics:          metrics.NewProxy("test"),
		Tracer:           telemetry.NoopTracer("proxy"),
		Validator:        validator,
		AgentVerifier:    passAgentVerifier{},
		Limiter:          ratelimit.Noop(),
		Health:           testHealthServer(),
		ProviderRegistry: reg,
		IdempotencyStore: store,
	})
}

func testRedisIdempotencyStore(t *testing.T) (idempotency.Store, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return idempotency.NewRedisStore(client, idempotency.Config{TTL: time.Hour}), mr
}

const chatBodyA = `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`
const chatBodyB = `{"model":"gpt-4o","messages":[{"role":"user","content":"bye"}]}`

func TestUnit_Idempotency_MissingHeaderCallsProvider(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, store, prov, nil)

	rec := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID,
	})
	assertStatus(t, rec, http.StatusOK)
	if prov.calls.Load() != 1 {
		t.Fatalf("Complete calls=%d want 1", prov.calls.Load())
	}
}

func TestUnit_Idempotency_DuplicateKeyReplaysWithoutSecondComplete(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		body: `{"choices":[{"message":{"role":"assistant","content":"once"}}]}`,
	}
	handler := idempotencyTestRouter(t, store, prov, nil)

	opts := chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "key-1",
	}
	rec1 := postChat(t, handler, opts)
	assertStatus(t, rec1, http.StatusOK)
	rec2 := postChat(t, handler, opts)
	assertStatus(t, rec2, http.StatusOK)
	if rec1.Body.String() != rec2.Body.String() {
		t.Fatalf("replay body mismatch:\n%s\nvs\n%s", rec1.Body.String(), rec2.Body.String())
	}
	if prov.calls.Load() != 1 {
		t.Fatalf("Complete calls=%d want 1", prov.calls.Load())
	}
}

func TestUnit_Idempotency_SameKeyDifferentBodyConflict(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, store, prov, nil)

	rec1 := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "reuse",
	})
	assertStatus(t, rec1, http.StatusOK)
	rec2 := postChat(t, handler, chatRequestOpts{
		body: chatBodyB, auth: true, agentID: testChatAgentID, idempotencyKey: "reuse",
	})
	assertStatus(t, rec2, http.StatusConflict)
	assertBodyCode(t, rec2, apierror.CodeIdempotencyKeyReuse)
	if prov.calls.Load() != 1 {
		t.Fatalf("Complete calls=%d want 1", prov.calls.Load())
	}
}

func TestUnit_Idempotency_InProgressConflict(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	block := make(chan struct{})
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}, blockCh: block}
	handler := idempotencyTestRouter(t, store, prov, nil)

	done := make(chan *httptest.ResponseRecorder, 1)
	go func() {
		done <- postChat(t, handler, chatRequestOpts{
			body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "inflight",
		})
	}()
	waitForCompleteCalls(t, prov, 1)
	rec2 := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "inflight",
	})
	assertStatus(t, rec2, http.StatusConflict)
	assertBodyCode(t, rec2, apierror.CodeIdempotencyInProgress)
	close(block)
	rec1 := <-done
	assertStatus(t, rec1, http.StatusOK)
	if prov.calls.Load() != 1 {
		t.Fatalf("Complete calls=%d want 1", prov.calls.Load())
	}
}

func TestUnit_Idempotency_CrossOrgIsolation(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	orgB := "550e8400-e29b-41d4-a716-446655440099"

	handlerA := idempotencyTestRouter(t, store, prov, defaultChatValidator())
	handlerB := idempotencyTestRouter(t, store, prov, &chatMockValidator{
		res: &auth.ValidateResult{OrgID: orgB, Permissions: permissions.ProxyChatCompletion},
	})

	recA := postChat(t, handlerA, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "shared",
	})
	assertStatus(t, recA, http.StatusOK)
	recB := postChat(t, handlerB, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "shared",
	})
	assertStatus(t, recB, http.StatusOK)
	if prov.calls.Load() != 2 {
		t.Fatalf("Complete calls=%d want 2 (cross-org)", prov.calls.Load())
	}
}

func TestUnit_Idempotency_StreamWithKeyRejected(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, store, prov, nil)

	rec := postChat(t, handler, chatRequestOpts{
		body:           `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}],"stream":true}`,
		auth:           true,
		agentID:        testChatAgentID,
		idempotencyKey: "stream-key",
	})
	assertStatus(t, rec, http.StatusBadRequest)
	assertBodyCode(t, rec, apierror.CodeValidationError)
	if prov.calls.Load() != 0 {
		t.Fatalf("Complete calls=%d want 0", prov.calls.Load())
	}
}

func TestUnit_Idempotency_KeyTooLong(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, store, prov, nil)

	longKey := strings.Repeat("a", maxIdempotencyKeyLen+1)
	if utf8.RuneCountInString(longKey) <= maxIdempotencyKeyLen {
		t.Fatal("test key not long enough")
	}
	rec := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: longKey,
	})
	assertStatus(t, rec, http.StatusBadRequest)
	assertBodyCode(t, rec, apierror.CodeValidationError)
	if prov.calls.Load() != 0 {
		t.Fatalf("Complete calls=%d want 0", prov.calls.Load())
	}
}

func TestUnit_Idempotency_RedisFailOpen(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	store := idempotency.NewRedisStore(client, idempotency.Config{TTL: time.Hour})
	mr.Close() // fail Redis after store construction

	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, store, prov, nil)
	rec := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "fail-open",
	})
	assertStatus(t, rec, http.StatusOK)
	if prov.calls.Load() != 1 {
		t.Fatalf("Complete calls=%d want 1", prov.calls.Load())
	}
}

func TestUnit_Idempotency_NoopStoreNoDedupe(t *testing.T) {
	t.Parallel()
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, idempotency.Noop(), prov, nil)
	opts := chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "noop",
	}
	assertStatus(t, postChat(t, handler, opts), http.StatusOK)
	assertStatus(t, postChat(t, handler, opts), http.StatusOK)
	if prov.calls.Load() != 2 {
		t.Fatalf("Complete calls=%d want 2 with Noop", prov.calls.Load())
	}
}

func TestUnit_FingerprintChatRequest_Stable(t *testing.T) {
	t.Parallel()
	parsed := mustParseChatBody(t, chatBodyA)
	fp1, err := fingerprintChatRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	fp2, err := fingerprintChatRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	if fp1 != fp2 || fp1 == "" {
		t.Fatalf("fingerprint unstable: %q %q", fp1, fp2)
	}
	other := mustParseChatBody(t, chatBodyB)
	fp3, err := fingerprintChatRequest(other)
	if err != nil {
		t.Fatal(err)
	}
	if fp1 == fp3 {
		t.Fatal("different bodies must differ in fingerprint")
	}
}

func assertStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status: got %d want %d body=%s", rec.Code, want, rec.Body.String())
	}
}

func assertBodyCode(t *testing.T, rec *httptest.ResponseRecorder, code apierror.Code) {
	t.Helper()
	if !strings.Contains(rec.Body.String(), string(code)) {
		t.Fatalf("body missing %s: %s", code, rec.Body.String())
	}
}

func waitForCompleteCalls(t *testing.T, prov *countingLLMProvider, want int64) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if prov.calls.Load() >= want {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for Complete calls=%d want %d", prov.calls.Load(), want)
}

func mustParseChatBody(t *testing.T, body string) *llm.ChatCompletionRequest {
	t.Helper()
	parsed, err := llm.ParseChatCompletionRequest(strings.NewReader(body))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	return parsed
}
