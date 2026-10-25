package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/idempotency"
	"github.com/Rick1330/ibex-harness/packages/session"
	"github.com/google/uuid"
)

type terminateLedgerFake struct {
	outcome     idempotency.ClaimOutcome
	claimErr    error
	finalizeErr error
}

func (f *terminateLedgerFake) Claim(context.Context, idempotency.Principal, string, string) (idempotency.ClaimOutcome, error) {
	return f.outcome, f.claimErr
}
func (f *terminateLedgerFake) Finalize(context.Context, idempotency.ClaimToken, int, []byte) error {
	return f.finalizeErr
}

func (f *terminateLedgerFake) Release(context.Context, idempotency.ClaimToken) error {
	return nil
}

func TestSessionTerminateLedgerBranches(t *testing.T) {
	runTerminateKeyValidationBranches(t)
	runTerminateLedgerOutcomeBranches(t)
}

func terminateLedgerBranchFixture(t *testing.T, ledger idempotency.Ledger, sid uuid.UUID) (sessionTerminateHandler, *terminateStoreFake) {
	store := &terminateStoreFake{result: session.CompleteOK, sessionID: sid}
	return newTerminateHandler(t, terminateHandlerArgs{store: store, metric: "ledger-branches", ledger: ledger}), store
}

func terminateLedgerBranchRequest(t *testing.T, org, agent uuid.UUID, key string) *http.Request {
	return terminateAuthedRequest(t, terminateReqParams{org: org, agent: agent, externalID: "ledger-ext", body: `{"status":"completed"}`, idempotencyKey: key})
}

func runTerminateKeyValidationBranches(t *testing.T) {
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	base := func(ledger idempotency.Ledger) (sessionTerminateHandler, *terminateStoreFake) {
		return terminateLedgerBranchFixture(t, ledger, sid)
	}
	request := func(key string) *http.Request {
		return terminateLedgerBranchRequest(t, org, agent, key)
	}

	t.Run("missing key", func(t *testing.T) {
		h, store := base(&terminateLedgerFake{})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request(""))
		if rec.Code != http.StatusBadRequest || store.calls.Load() != 0 {
			t.Fatalf("status=%d calls=%d", rec.Code, store.calls.Load())
		}
	})
	t.Run("oversized key", func(t *testing.T) {
		h, store := base(&terminateLedgerFake{})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request(strings.Repeat("k", 257)))
		if rec.Code != http.StatusBadRequest || store.calls.Load() != 0 {
			t.Fatalf("status=%d calls=%d", rec.Code, store.calls.Load())
		}
	})
	t.Run("claim failure", func(t *testing.T) {
		h, store := base(&terminateLedgerFake{claimErr: errors.New("ledger down")})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request("claim-failure"))
		if rec.Code != http.StatusServiceUnavailable || store.calls.Load() != 0 {
			t.Fatalf("status=%d calls=%d", rec.Code, store.calls.Load())
		}
	})
}

func runTerminateLedgerOutcomeBranches(t *testing.T) {
	org, agent, sid := uuid.New(), uuid.New(), uuid.New()
	base := func(ledger idempotency.Ledger) (sessionTerminateHandler, *terminateStoreFake) {
		return terminateLedgerBranchFixture(t, ledger, sid)
	}
	request := func(key string) *http.Request {
		return terminateLedgerBranchRequest(t, org, agent, key)
	}
	t.Run("replay", func(t *testing.T) {
		h, store := base(&terminateLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimReplay, Status: http.StatusOK, Response: []byte(`{"data":{"replayed":true}}`)}})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request("replay"))
		if rec.Code != http.StatusOK || rec.Body.String() != `{"data":{"replayed":true}}` {
			t.Fatalf("status=%d body=%q", rec.Code, rec.Body.String())
		}
		if store.calls.Load() != 1 {
			t.Fatalf("replay recovery calls=%d want 1", store.calls.Load())
		}
	})
	t.Run("conflict", func(t *testing.T) {
		h, store := base(&terminateLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimConflict}})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request("conflict"))
		if rec.Code != http.StatusConflict || store.calls.Load() != 0 {
			t.Fatalf("status=%d calls=%d", rec.Code, store.calls.Load())
		}
	})
	t.Run("in progress", func(t *testing.T) {
		h, store := base(&terminateLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimInProgress, RetryAfter: 2 * time.Second}})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request("in-progress"))
		if rec.Code != http.StatusConflict || rec.Header().Get("Retry-After") != "3" || store.calls.Load() != 0 {
			t.Fatalf("status=%d retry=%q calls=%d", rec.Code, rec.Header().Get("Retry-After"), store.calls.Load())
		}
	})
	t.Run("finalize failure", func(t *testing.T) {
		claim := idempotency.ClaimToken{ID: uuid.New(), Principal: idempotency.Principal{OrgID: org, AgentID: agent}, Key: "finalize-failure", RequestHash: "hash", Version: 1}
		h, store := base(&terminateLedgerFake{outcome: idempotency.ClaimOutcome{Kind: idempotency.ClaimOwned, Claim: claim}, finalizeErr: errors.New("finalize down")})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, request("finalize-failure"))
		if rec.Code != http.StatusServiceUnavailable || store.calls.Load() != 1 {
			t.Fatalf("status=%d calls=%d", rec.Code, store.calls.Load())
		}
	})
}

func TestSessionTerminateReplayRecoveryFailureBranches(t *testing.T) {
	id := terminateIdentity{orgID: uuid.New(), agentID: uuid.New(), externalID: "recovery-ext"}
	var nilHandler sessionTerminateHandler
	nilHandler.recoverReplayEnqueue(context.Background(), id)
	errHandler := sessionTerminateHandler{store: &terminateStoreFake{err: errors.New("lookup failed")}}
	errHandler.recoverReplayEnqueue(context.Background(), id)
	notFoundHandler := sessionTerminateHandler{store: &terminateStoreFake{result: session.CompleteNotFound}}
	notFoundHandler.recoverReplayEnqueue(context.Background(), id)
}
