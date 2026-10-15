package chat

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

type chatLedgerFake struct {
	outcome   idempotency.ClaimOutcome
	claimErr  error
	finalErr  error
	principal idempotency.Principal
	key       string
	hash      string
	finalized bool
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
	if fake.hash == "" || fake.hash[:5] != "chat\x00" {
		t.Fatalf("hash=%q does not identify the chat mutation", fake.hash)
	}
	id.Finish(claim, http.StatusOK, []byte(`{"ok":true}`))
	if !fake.finalized {
		t.Fatal("expected durable finalize")
	}
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
				return
			}
			if cont || claim != nil || rec.Code != tc.wantStatus {
				t.Fatalf("conflict claim=%#v cont=%v status=%d", claim, cont, rec.Code)
			}
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
