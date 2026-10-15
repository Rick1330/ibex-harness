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

func TestDurableChatLedgerReplayAndConflict(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	for name, tc := range map[string]struct {
		outcome    idempotency.ClaimOutcome
		wantStatus int
	}{
		"replay":   {outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimReplay, Status: 201, Response: []byte(`{"ok":true}`)}, wantStatus: 201},
		"conflict": {outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimConflict}, wantStatus: http.StatusConflict},
	} {
		t.Run(name, func(t *testing.T) {
			fake := &chatLedgerFake{outcome: tc.outcome}
			id := durableChatID(t, fake)
			req, parsed := durableChatRequest(org, agent, "chat-key")
			rec := httptest.NewRecorder()
			claim, cont := id.Resolve(rec, req, parsed)
			if name == "replay" {
				if !cont || claim == nil || !claim.Replay || claim.Hit.Status != tc.wantStatus {
					t.Fatalf("replay claim=%#v cont=%v status=%d", claim, cont, rec.Code)
				}
				assertChatMetric(t, id.Metrics, metrics.IdempotencyHit)
				return
			}
			if cont || claim != nil || rec.Code != tc.wantStatus {
				t.Fatalf("conflict claim=%#v cont=%v status=%d", claim, cont, rec.Code)
			}
			assertChatMetric(t, id.Metrics, metrics.IdempotencyConflict)
		})
	}
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

func TestDurableChatLedgerFailureAndMissingKeyFailClosed(t *testing.T) {
	org, agent := uuid.New(), uuid.New()
	for name, tc := range map[string]struct {
		ledger     idempotency.Ledger
		key        string
		wantStatus int
	}{
		"claim failure": {ledger: &chatLedgerFake{claimErr: errors.New("database unavailable")}, key: "chat-key", wantStatus: http.StatusServiceUnavailable},
		"missing key":   {ledger: &chatLedgerFake{}, key: "", wantStatus: http.StatusBadRequest},
	} {
		t.Run(name, func(t *testing.T) {
			id := durableChatID(t, tc.ledger)
			req, parsed := durableChatRequest(org, agent, tc.key)
			rec := httptest.NewRecorder()
			claim, cont := id.Resolve(rec, req, parsed)
			if cont || claim != nil || rec.Code != tc.wantStatus {
				t.Fatalf("claim=%#v cont=%v status=%d want=%d", claim, cont, rec.Code, tc.wantStatus)
			}
		})
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
