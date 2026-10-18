package chat

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
	dto "github.com/prometheus/client_model/go"
)

type chatLedgerFake struct {
	outcome    idempotency.ClaimOutcome
	claimErr   error
	finalErr   error
	releaseErr error
	released   bool
	principal  idempotency.Principal
	key        string
	hash       string
	finalized  bool
}

func (f *chatLedgerFake) Claim(_ context.Context, p idempotency.Principal, key, hash string) (idempotency.ClaimOutcome, error) {
	f.principal, f.key, f.hash = p, key, hash
	if f.claimErr != nil {
		return idempotency.ClaimOutcome{}, f.claimErr
	}
	return f.outcome, nil
}

func (f *chatLedgerFake) Finalize(_ context.Context, _ idempotency.ClaimToken, _ int, _ []byte) error {
	f.finalized = true
	return f.finalErr
}

func (f *chatLedgerFake) Release(_ context.Context, _ idempotency.ClaimToken) error {
	f.released = true
	return f.releaseErr
}

type tenantChatLedgerFake struct {
	finalizedOrg uuid.UUID
}

func (f *tenantChatLedgerFake) Claim(_ context.Context, p idempotency.Principal, key, hash string) (idempotency.ClaimOutcome, error) {
	if f.finalizedOrg == p.OrgID {
		return idempotency.ClaimOutcome{Kind: idempotency.ClaimReplay, Status: http.StatusOK, Response: []byte(`{"org":"a"}`)}, nil
	}
	return idempotency.ClaimOutcome{Kind: idempotency.ClaimOwned, Claim: idempotency.ClaimToken{
		ID: uuid.New(), Principal: p, Key: key, RequestHash: hash, Version: 1,
	}}, nil
}

func (f *tenantChatLedgerFake) Finalize(_ context.Context, claim idempotency.ClaimToken, _ int, _ []byte) error {
	f.finalizedOrg = claim.Principal.OrgID
	return nil
}

func (f *tenantChatLedgerFake) Release(context.Context, idempotency.ClaimToken) error { return nil }

func durableChatID(t *testing.T, ledger idempotency.Ledger) Idempotency {
	t.Helper()
	return Idempotency{
		Ledger: ledger, Metrics: metrics.NewProxy("chat-ledger-test"),
		Log: logger.Discard("chat-ledger-test"), Timeout: time.Second,
	}
}

func durableChatRequest(org, agent uuid.UUID, key string) (*http.Request, *llm.ChatCompletionRequest) {
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set(idempotencyHeader, key)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: org, AgentID: agent}))
	return req, &llm.ChatCompletionRequest{Model: "gpt-test", Messages: []llm.Message{{Role: "user", Content: "hello"}}}
}

type recordingIDStore struct {
	released  bool
	committed bool
}

func (s *recordingIDStore) Claim(context.Context, idempotency.Token, idempotency.Fingerprint) (idempotency.Outcome, error) {
	return idempotency.Outcome{}, nil
}

func (s *recordingIDStore) Commit(context.Context, idempotency.Token, idempotency.Record) error {
	s.committed = true
	return nil
}

func (s *recordingIDStore) Release(context.Context, idempotency.Token, idempotency.Fingerprint) error {
	s.released = true
	return nil
}

func TestAbandonLedgerPathReleasesWithoutFinalize(t *testing.T) {
	fake := &chatLedgerFake{}
	id := durableChatID(t, fake)
	claim := &Claim{OrgID: uuid.New(), Key: "abandon-key", Ledger: &idempotency.ClaimToken{ID: uuid.New(), Version: 1}}
	id.Abandon(claim)
	if !fake.released || fake.finalized {
		t.Fatalf("released=%v finalized=%v", fake.released, fake.finalized)
	}
}

func TestAbandonNilClaimIsNoop(t *testing.T) {
	id := durableChatID(t, &chatLedgerFake{})
	id.Abandon(nil)
}

func TestAbandonPrefersStoreWhenClaimHasNoLedgerToken(t *testing.T) {
	ledger := &chatLedgerFake{}
	store := &recordingIDStore{}
	id := Idempotency{
		Ledger: ledger, Store: store,
		Metrics: metrics.NewProxy("chat-abandon-test"), Log: logger.Discard("chat-abandon-test"),
		Timeout: time.Second,
	}
	claim := &Claim{OrgID: uuid.New(), Key: "abandon-key", FP: idempotency.Fingerprint("fp")}
	id.Abandon(claim)
	if !store.released || store.committed {
		t.Fatalf("store released=%v committed=%v", store.released, store.committed)
	}
	if ledger.released || ledger.finalized {
		t.Fatalf("ledger released=%v finalized=%v", ledger.released, ledger.finalized)
	}
}

func TestDurableChatLedgerOwnedAndFinalized(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimOwned, Claim: idempotency.ClaimToken{ID: uuid.New(), Version: 1}}}
	id := durableChatID(t, fake)
	req, parsed := durableChatRequest(org, agent, "chat-key")
	claim, cont := id.Resolve(httptest.NewRecorder(), req, parsed)
	if !cont || claim == nil || claim.Ledger == nil {
		t.Fatalf("owned claim=%#v cont=%v", claim, cont)
	}
	if fake.principal != (idempotency.Principal{OrgID: org, AgentID: agent}) || fake.key != "chat-key" {
		t.Fatalf("principal/key=%+v/%q", fake.principal, fake.key)
	}
	if len(fake.hash) != 64 {
		t.Fatalf("hash=%q is not a 64-character ledger hash", fake.hash)
	}
	id.Finish(claim, http.StatusOK, []byte(`{"ok":true}`))
	if !fake.finalized {
		t.Fatal("expected durable finalize")
	}
	assertChatMetric(t, id.Metrics, metrics.IdempotencyMiss)
}

func TestDurableChatFingerprintIncludesNormalizedSkipMemoryMode(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimOwned, Claim: idempotency.ClaimToken{ID: uuid.New(), Version: 1}}}
	id := durableChatID(t, fake)
	parsed := &llm.ChatCompletionRequest{Model: "gpt-test", Messages: []llm.Message{{Role: "user", Content: "hello"}}}
	withoutHeader, _ := durableChatRequest(org, agent, "without-header")
	if claim, cont := id.Resolve(httptest.NewRecorder(), withoutHeader, parsed); !cont || claim == nil {
		t.Fatal("baseline durable claim failed")
	}
	baseline := fake.hash
	withTruthyHeader, _ := durableChatRequest(org, agent, "truthy-header")
	withTruthyHeader.Header.Set(validation.HeaderSkipMemory, " TRUE ")
	if claim, cont := id.Resolve(httptest.NewRecorder(), withTruthyHeader, parsed); !cont || claim == nil {
		t.Fatal("truthy durable claim failed")
	}
	truthy := fake.hash
	if baseline == truthy {
		t.Fatal("skip-memory mode must change the durable request fingerprint")
	}
	withEquivalentHeader, _ := durableChatRequest(org, agent, "equivalent-header")
	withEquivalentHeader.Header.Set(validation.HeaderSkipMemory, "on")
	if claim, cont := id.Resolve(httptest.NewRecorder(), withEquivalentHeader, parsed); !cont || claim == nil {
		t.Fatal("equivalent durable claim failed")
	}
	if truthy != fake.hash {
		t.Fatal("equivalent truthy skip-memory values must share a fingerprint")
	}
}

func TestDurableChatLedgerReplay(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimReplay, Status: 201, Response: []byte(`{"ok":true}`)}}
	id := durableChatID(t, fake)
	req, parsed := durableChatRequest(org, agent, "chat-key")
	rec := httptest.NewRecorder()
	claim, cont := id.Resolve(rec, req, parsed)
	if !cont || claim == nil || !claim.Replay || claim.Hit.Status != http.StatusCreated {
		t.Fatalf("replay claim=%#v cont=%v status=%d", claim, cont, rec.Code)
	}
	assertChatMetric(t, id.Metrics, metrics.IdempotencyHit)
}

func TestDurableChatLedgerConflict(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimConflict}}
	id := durableChatID(t, fake)
	req, parsed := durableChatRequest(org, agent, "chat-key")
	rec := httptest.NewRecorder()
	claim, cont := id.Resolve(rec, req, parsed)
	if cont || claim != nil || rec.Code != http.StatusConflict {
		t.Fatalf("conflict claim=%#v cont=%v status=%d", claim, cont, rec.Code)
	}
	assertChatMetric(t, id.Metrics, metrics.IdempotencyConflict)
}

func TestDurableChatLedgerInProgressReturnsRetryAfter(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimInProgress, RetryAfter: 2 * time.Second}}
	id := durableChatID(t, fake)
	req, parsed := durableChatRequest(org, agent, "chat-key")
	rec := httptest.NewRecorder()
	claim, cont := id.Resolve(rec, req, parsed)
	if cont || claim != nil || rec.Code != http.StatusConflict {
		t.Fatalf("claim=%#v cont=%v status=%d", claim, cont, rec.Code)
	}
	if got := rec.Header().Get("Retry-After"); got != "3" {
		t.Fatalf("Retry-After=%q want 3", got)
	}
	assertChatMetric(t, id.Metrics, metrics.IdempotencyInProgress)
}

func assertChatMetric(t *testing.T, reg *metrics.ProxyRegistry, result string) {
	t.Helper()
	families, err := reg.Gatherer().Gather()
	if err != nil {
		t.Fatalf("gather metrics: %v", err)
	}
	for _, family := range families {
		if family.GetName() != "ibex_proxy_idempotency_total" {
			continue
		}
		for _, metric := range family.GetMetric() {
			if metricLabel(metric, "result") == result && metric.GetCounter().GetValue() != 0 {
				return
			}
		}
	}
	t.Fatalf("idempotency metric %q was not incremented", result)
}

func metricLabel(metric *dto.Metric, name string) string {
	for _, label := range metric.GetLabel() {
		if label.GetName() == name {
			return label.GetValue()
		}
	}
	return ""
}

func TestDurableChatLedgerClaimFailureFailsClosed(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	id := durableChatID(t, &chatLedgerFake{claimErr: errors.New("database unavailable")})
	req, parsed := durableChatRequest(org, agent, "chat-key")
	rec := httptest.NewRecorder()
	claim, cont := id.Resolve(rec, req, parsed)
	if cont || claim != nil || rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("claim=%#v cont=%v status=%d", claim, cont, rec.Code)
	}
}

func TestDurableChatLedgerMissingKeyFailsClosed(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	id := durableChatID(t, &chatLedgerFake{})
	req, parsed := durableChatRequest(org, agent, "")
	rec := httptest.NewRecorder()
	claim, cont := id.Resolve(rec, req, parsed)
	if cont || claim != nil || rec.Code != http.StatusBadRequest {
		t.Fatalf("claim=%#v cont=%v status=%d", claim, cont, rec.Code)
	}
}

func TestDurableChatLedgerRequiresAuthenticatedPrincipal(t *testing.T) {
	org := uuid.New()
	id := durableChatID(t, &chatLedgerFake{})
	tests := map[string]*http.Request{
		"missing auth":  httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil),
		"missing agent": httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(auth.WithContext(context.Background(), &auth.ValidateResult{OrgID: org})),
	}
	for name, req := range tests {
		t.Run(name, func(t *testing.T) {
			req.Header.Set(idempotencyHeader, "chat-key")
			rec := httptest.NewRecorder()
			claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "gpt-test"})
			if cont || claim != nil || rec.Code != http.StatusServiceUnavailable {
				t.Fatalf("claim=%#v cont=%v status=%d", claim, cont, rec.Code)
			}
		})
	}
}

func TestDurableChatLedgerStreamIsRejected(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	id := durableChatID(t, &chatLedgerFake{})
	req, _ := durableChatRequest(org, agent, "stream-key")
	rec := httptest.NewRecorder()
	claim, cont := id.Resolve(rec, req, &llm.ChatCompletionRequest{Model: "gpt-test", Stream: true})
	if cont || claim != nil || rec.Code != http.StatusBadRequest {
		t.Fatalf("claim=%#v cont=%v status=%d", claim, cont, rec.Code)
	}
}

func TestDurableChatLedgerTransientFailureReleasesOwnedClaim(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{
		Kind:  idempotency.ClaimOwned,
		Claim: idempotency.ClaimToken{ID: uuid.New(), Version: 1},
	}}
	id := durableChatID(t, fake)
	req, parsed := durableChatRequest(org, agent, "retry-key")
	claim, cont := id.Resolve(httptest.NewRecorder(), req, parsed)
	if !cont || claim == nil {
		t.Fatalf("claim=%#v cont=%v", claim, cont)
	}
	id.Finish(claim, http.StatusBadGateway, []byte(`{"error":"temporary"}`))
	if !fake.released || fake.finalized {
		t.Fatalf("released=%v finalized=%v", fake.released, fake.finalized)
	}
}

func TestDurableChatLedgerFinalizeAndReleaseFailuresAreHandled(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	t.Run("finalize failure", func(t *testing.T) {
		fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{
			Kind:  idempotency.ClaimOwned,
			Claim: idempotency.ClaimToken{ID: uuid.New(), Version: 1},
		}, finalErr: errors.New("finalize unavailable")}
		id := durableChatID(t, fake)
		req, parsed := durableChatRequest(org, agent, "finalize-failure")
		claim, cont := id.Resolve(httptest.NewRecorder(), req, parsed)
		if !cont || claim == nil {
			t.Fatalf("claim=%#v cont=%v", claim, cont)
		}
		id.Finish(claim, http.StatusOK, []byte(`{"ok":true}`))
		if !fake.finalized {
			t.Fatal("expected finalize attempt")
		}
	})
	t.Run("oversize release and release failure", func(t *testing.T) {
		fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{
			Kind:  idempotency.ClaimOwned,
			Claim: idempotency.ClaimToken{ID: uuid.New(), Version: 1},
		}, releaseErr: errors.New("release unavailable")}
		id := durableChatID(t, fake)
		req, parsed := durableChatRequest(org, agent, "oversize")
		claim, cont := id.Resolve(httptest.NewRecorder(), req, parsed)
		if !cont || claim == nil {
			t.Fatalf("claim=%#v cont=%v", claim, cont)
		}
		body := []byte(strings.Repeat("x", int(validation.MaxProviderResponseBytes)+1))
		id.Finish(claim, http.StatusOK, body)
		if !fake.released {
			t.Fatal("expected oversize response to release claim")
		}
	})
}

func TestDurableChatFinishNoopAndCaptureRelease(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	fake := &chatLedgerFake{outcome: idempotency.ClaimOutcome{
		Kind:  idempotency.ClaimOwned,
		Claim: idempotency.ClaimToken{ID: uuid.New(), Version: 1},
	}}
	id := durableChatID(t, fake)
	id.Finish(nil, http.StatusOK, []byte(`{}`))

	req, parsed := durableChatRequest(org, agent, "capture-release")
	claim, cont := id.Resolve(httptest.NewRecorder(), req, parsed)
	if !cont || claim == nil {
		t.Fatalf("claim=%#v cont=%v", claim, cont)
	}
	cw := &CapturingWriter{ResponseWriter: httptest.NewRecorder()}
	_, _ = cw.Write([]byte(strings.Repeat("x", int(validation.MaxProviderResponseBytes)+1)))
	id.FinishCapture(claim, cw)
	if !fake.released {
		t.Fatal("expected capped capture to release durable claim")
	}
}

func TestDurableChatLedgerDoesNotReplayAcrossTenants(t *testing.T) {
	orgA, orgB, agent := uuid.New(), uuid.New(), uuid.New()
	fake := &tenantChatLedgerFake{}
	id := durableChatID(t, fake)
	reqA, parsed := durableChatRequest(orgA, agent, "same-key")
	claimA, cont := id.Resolve(httptest.NewRecorder(), reqA, parsed)
	if !cont || claimA == nil || claimA.Replay {
		t.Fatalf("organization A claim=%#v cont=%v", claimA, cont)
	}
	id.Finish(claimA, http.StatusOK, []byte(`{"org":"a"}`))
	reqB, parsedB := durableChatRequest(orgB, agent, "same-key")
	claimB, cont := id.Resolve(httptest.NewRecorder(), reqB, parsedB)
	if !cont || claimB == nil || claimB.Replay || claimB.OrgID != orgB {
		t.Fatalf("organization B claim=%#v cont=%v", claimB, cont)
	}
}
