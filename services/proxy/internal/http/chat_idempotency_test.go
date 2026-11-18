package http

import (
	"context"
	"errors"
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
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	httpchat "github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type countingLLMProvider struct {
	name      string
	models    []string
	body      string
	err       error
	calls     atomic.Int64
	blockCh   chan struct{} // optional: hold Complete until closed
	startedCh chan struct{} // optional: closed once on first Complete entry
}

func (s *countingLLMProvider) Complete(ctx context.Context, _ provider.Request) (provider.Response, error) {
	s.calls.Add(1)
	if s.startedCh != nil {
		select {
		case <-s.startedCh:
		default:
			close(s.startedCh)
		}
	}
	if s.blockCh != nil {
		select {
		case <-s.blockCh:
		case <-ctx.Done():
			return provider.Response{}, ctx.Err()
		}
	}
	if s.err != nil {
		return provider.Response{}, s.err
	}
	body := s.body
	if body == "" {
		body = minimalValidChatCompletionJSON
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
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), prov)
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	if validator == nil {
		validator = defaultChatValidator()
	}
	cfg := chatTestConfig()
	cfg.IdempotencyTTL = time.Hour
	cfg.IdempotencyRedisTimeout = time.Second
	return mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config = cfg
		d.Validator = validator
		d.ProviderRegistry = reg
		d.IdempotencyStore = store
	}))
}

func testRedisIdempotencyStore(t *testing.T) (idempotency.Store, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	store, err := idempotency.NewRedisStore(client, idempotency.Config{TTL: time.Hour})
	if err != nil {
		t.Fatalf("NewRedisStore: %v", err)
	}
	return store, mr
}

// recordingTerminationLedger is the durable ledger the v1 profile wires, in the
// smallest form that lets the router exercise it: it owns every key it is asked
// for and records what it was given. The chat package keeps its own fake, but it
// is unexported there, and a router-level test has to build the router to reach
// the path at all.
type recordingTerminationLedger struct {
	principals []idempotency.Principal
	keys       []string
	finalized  int
}

func (l *recordingTerminationLedger) Claim(_ context.Context, p idempotency.Principal, key, hash string) (idempotency.ClaimOutcome, error) {
	l.principals = append(l.principals, p)
	l.keys = append(l.keys, key)
	return idempotency.ClaimOutcome{Kind: idempotency.ClaimOwned, Claim: idempotency.ClaimToken{
		ID: uuid.New(), Principal: p, Key: key, RequestHash: hash, Version: 1,
	}}, nil
}

func (l *recordingTerminationLedger) Finalize(context.Context, idempotency.ClaimToken, int, []byte) error {
	l.finalized++
	return nil
}

func (l *recordingTerminationLedger) Release(context.Context, idempotency.ClaimToken) error {
	return nil
}

// durableLedgerRouter builds the router the way the v1 profile does: a
// registered provider, a provider-scoped token that names its agent, and a
// non-nil TerminationLedger. That last field is the one every other harness
// leaves nil, which is why the required-header path had no router-level test.
func durableLedgerRouter(t *testing.T, ledger idempotency.Ledger, prov provider.Provider) http.Handler {
	t.Helper()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog(), prov)
	if err != nil {
		t.Fatalf("NewRegistry: %v", err)
	}
	cfg := chatTestConfig()
	cfg.IdempotencyRedisTimeout = time.Second
	validator := &chatMockValidator{res: &auth.ValidateResult{
		OrgID:       uuid.MustParse(testChatOrgID),
		AgentID:     uuid.MustParse(testChatAgentID),
		Permissions: permissions.ProxyChatCompletion,
	}}
	return mustNewRouter(t, mergeRouterDeps(defaultChatRouterDeps(t), func(d *RouterDeps) {
		d.Config = cfg
		d.Validator = validator
		d.ProviderRegistry = reg
		d.TerminationLedger = ledger
	}))
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

// TestUnit_Idempotency_DurableLedgerRequiresHeader pins the contract the v1
// profile runs under: with the durable ledger wired, a non-streaming chat
// completion without an Idempotency-Key is refused before the provider call, and
// one with the key goes through and finalizes its claim.
//
// Every other harness in this package leaves TerminationLedger nil, so the chat
// route answered 200 without the header and nothing caught that the wired
// profile answers 400. The v1 smoke found it in CI instead.
func TestUnit_Idempotency_DurableLedgerRequiresHeader(t *testing.T) {
	t.Parallel()
	ledger := &recordingTerminationLedger{}
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := durableLedgerRouter(t, ledger, prov)

	assertDurableHeaderRefused(t, handler, prov, ledger)
	assertDurableKeyClaimsOnce(t, handler, prov, ledger)
}

// assertDurableHeaderRefused pins that a completion without an Idempotency-Key is
// refused before the provider or the ledger is touched.
func assertDurableHeaderRefused(
	t *testing.T,
	handler http.Handler,
	prov *countingLLMProvider,
	ledger *recordingTerminationLedger,
) {
	t.Helper()
	rec := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID,
	})
	assertStatus(t, rec, http.StatusBadRequest)
	assertBodyCode(t, rec, apierror.CodeValidationError)
	if body := rec.Body.String(); !strings.Contains(body, `"field":"header.Idempotency-Key"`) {
		t.Fatalf("body does not name the required header: %s", body)
	}
	if calls := prov.calls.Load(); calls != 0 {
		t.Fatalf("Complete calls=%d want 0 without an Idempotency-Key", calls)
	}
	if len(ledger.keys) != 0 {
		t.Fatalf("ledger claimed %v without an Idempotency-Key", ledger.keys)
	}
}

// assertDurableKeyClaimsOnce pins that the same completion carrying the header
// past the refusals above reaches the provider and leaves exactly one finalized
// claim naming the key and the verified agent.
func assertDurableKeyClaimsOnce(
	t *testing.T,
	handler http.Handler,
	prov *countingLLMProvider,
	ledger *recordingTerminationLedger,
) {
	t.Helper()
	rec := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "durable-key-1",
	})
	assertStatus(t, rec, http.StatusOK)
	if calls := prov.calls.Load(); calls != 1 {
		t.Fatalf("Complete calls=%d want 1 past the header check", calls)
	}
	if len(ledger.keys) != 1 || ledger.keys[0] != "durable-key-1" {
		t.Fatalf("ledger claimed %v, want one claim for durable-key-1", ledger.keys)
	}
	if len(ledger.principals) != 1 || ledger.principals[0].AgentID != uuid.MustParse(testChatAgentID) {
		t.Fatalf("ledger principals=%+v, want the verified agent", ledger.principals)
	}
	if ledger.finalized != 1 {
		t.Fatalf("ledger finalized=%d want 1", ledger.finalized)
	}
}

func TestUnit_Idempotency_DuplicateKeyReplaysWithoutSecondComplete(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		body: `{"id":"test","object":"chat.completion","choices":[{"index":0,"message":{"role":"assistant","content":"once"},"finish_reason":"stop"}]}`,
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
	started := make(chan struct{})
	prov := &countingLLMProvider{
		name: "openai", models: []string{"gpt-4o"}, blockCh: block, startedCh: started,
	}
	handler := idempotencyTestRouter(t, store, prov, nil)

	done := make(chan *httptest.ResponseRecorder, 1)
	go func() {
		done <- postChat(t, handler, chatRequestOpts{
			body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "inflight",
		})
	}()
	waitForProviderStarted(t, started)
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

func TestUnit_Idempotency_TransientFailureAllowsRetry(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{
		name: "openai", models: []string{"gpt-4o"},
		err: errors.New("connection refused"),
	}
	handler := idempotencyTestRouter(t, store, prov, nil)
	opts := chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: "retry-me",
	}
	rec1 := postChat(t, handler, opts)
	assertStatus(t, rec1, http.StatusServiceUnavailable)

	prov.err = nil
	rec2 := postChat(t, handler, opts)
	assertStatus(t, rec2, http.StatusOK)
	if prov.calls.Load() != 2 {
		t.Fatalf("Complete calls=%d want 2 after transient release", prov.calls.Load())
	}
}

func TestUnit_Idempotency_CrossOrgIsolation(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	orgB := uuid.MustParse("550e8400-e29b-41d4-a716-446655440099")

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

func TestUnit_Idempotency_KeyRuneLengthBoundary(t *testing.T) {
	t.Parallel()
	store, _ := testRedisIdempotencyStore(t)
	prov := &countingLLMProvider{name: "openai", models: []string{"gpt-4o"}}
	handler := idempotencyTestRouter(t, store, prov, nil)

	okKey := strings.Repeat("字", 256)
	if utf8.RuneCountInString(okKey) != 256 {
		t.Fatalf("okKey runes=%d", utf8.RuneCountInString(okKey))
	}
	recOK := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: okKey,
	})
	assertStatus(t, recOK, http.StatusOK)

	longKey := strings.Repeat("字", 256+1)
	recBad := postChat(t, handler, chatRequestOpts{
		body: chatBodyA, auth: true, agentID: testChatAgentID, idempotencyKey: longKey,
	})
	assertStatus(t, recBad, http.StatusBadRequest)
	assertBodyCode(t, recBad, apierror.CodeValidationError)
	if prov.calls.Load() != 1 {
		t.Fatalf("Complete calls=%d want 1 (only accepted key)", prov.calls.Load())
	}
}

func TestUnit_Idempotency_RedisFailOpen(t *testing.T) {
	t.Parallel()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	store, err := idempotency.NewRedisStore(client, idempotency.Config{TTL: time.Hour})
	if err != nil {
		t.Fatalf("NewRedisStore: %v", err)
	}
	mr.Close()

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
	fp1, err := httpchat.FingerprintRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	fp2, err := httpchat.FingerprintRequest(parsed)
	if err != nil {
		t.Fatal(err)
	}
	if fp1 != fp2 || fp1 == "" {
		t.Fatalf("fingerprint unstable: %q %q", fp1, fp2)
	}
	other := mustParseChatBody(t, chatBodyB)
	fp3, err := httpchat.FingerprintRequest(other)
	if err != nil {
		t.Fatal(err)
	}
	if fp1 == fp3 {
		t.Fatal("different bodies must differ in fingerprint")
	}
}

func TestUnit_ShouldCommitIdempotency(t *testing.T) {
	t.Parallel()
	cases := []struct {
		status int
		want   bool
	}{
		{200, true},
		{400, true},
		{409, true},
		{429, false},
		{500, false},
		{504, false},
		{100, false},
	}
	for _, tc := range cases {
		if got := httpchat.ShouldCommit(tc.status); got != tc.want {
			t.Fatalf("status %d: got %v want %v", tc.status, got, tc.want)
		}
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

func waitForProviderStarted(t *testing.T, started <-chan struct{}) {
	t.Helper()
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for provider Complete to start")
	}
}

func mustParseChatBody(t *testing.T, body string) *llm.ChatCompletionRequest {
	t.Helper()
	parsed, err := llm.ParseChatCompletionRequest(strings.NewReader(body))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	return parsed
}
