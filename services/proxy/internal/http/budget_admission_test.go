package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/budgetledger"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

type finalizeCall struct {
	claim        budgetledger.Reservation
	cents        int64
	completeness budgetledger.Completeness
}

type fakeBudgetLedger struct {
	claimOut    budgetledger.ClaimOutcome
	claimErr    error
	claims      []budgetledger.ClaimRequest
	principals  []budgetledger.Principal
	finalized   []finalizeCall
	finalizeErr error
	releases    []budgetledger.Reservation
	releaseErr  error
}

func (f *fakeBudgetLedger) Claim(_ context.Context, p budgetledger.Principal, req budgetledger.ClaimRequest) (budgetledger.ClaimOutcome, error) {
	f.claims = append(f.claims, req)
	f.principals = append(f.principals, p)
	return f.claimOut, f.claimErr
}

func (f *fakeBudgetLedger) Finalize(_ context.Context, claim budgetledger.Reservation, cents int64, c budgetledger.Completeness) error {
	f.finalized = append(f.finalized, finalizeCall{claim: claim, cents: cents, completeness: c})
	return f.finalizeErr
}

func (f *fakeBudgetLedger) Release(_ context.Context, claim budgetledger.Reservation) error {
	f.releases = append(f.releases, claim)
	return f.releaseErr
}

func admissionCard() billing.CardVersion {
	return billing.CardVersion{
		Version: "7",
		Prices: []billing.PriceRow{{
			Provider: "mock", ModelPattern: "mock*",
			InputCentsPer1k: 100, OutputCentsPer1k: 200,
		}},
	}
}

func admissionMessages() []provider.Message {
	return []provider.Message{{Role: "user", Content: "hello budget"}}
}

func mockAdmissionInput(maxTokens int) budgetAdmissionInput {
	return budgetAdmissionInput{
		provider: "mock", model: "mock-1", messages: admissionMessages(), maxTokens: maxTokens,
	}
}

func settleSuccess(ctx context.Context, h chatCompletionHandler, usage *provider.Usage) {
	h.settleBudgetOutcome(ctx, budgetSettlement{
		status: http.StatusOK, provider: "mock", model: "mock-1", usage: usage,
	})
}

func budgetRequest(org, agent uuid.UUID) *http.Request {
	ctx := auth.WithContext(context.Background(), &auth.ValidateResult{OrgID: org, AgentID: agent})
	ctx = WithAgent(ctx, auth.AgentRecord{ID: agent, OrgID: org, Status: "active"})
	ctx = WithRequestID(ctx, "req-123")
	return httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
}

func admissionHandler(t *testing.T, ledger budgetledger.Ledger, snap billing.BudgetSnapshot) chatCompletionHandler {
	t.Helper()
	return chatCompletionHandler{
		metrics:      metrics.NewProxy("proxy-test"),
		docsBase:     "https://docs.example.com",
		budgetCache:  newBudgetCache(t, stubBudgetLoader{snap: snap}),
		budgetLedger: ledger,
	}
}

func hardCapSnapshot(card billing.CardVersion) billing.BudgetSnapshot {
	return billing.BudgetSnapshot{
		HasHardCap: true, CapCents: 10_000, SpentCents: 100,
		EnforcementMode: billing.EnforcementHardCap, PublishedCard: card,
	}
}

func TestUnit_EstimateInputTokens(t *testing.T) {
	t.Parallel()
	got := estimateInputTokens([]provider.Message{
		{Role: "system", Content: "0123456789"}, // 10 bytes/runes -> 10
		{Role: "user", Content: ""},             // 0
		{Role: "user", Content: "é"},            // 2 bytes, 1 rune -> max(0,1)=1
	})
	if got != (4+10)+(4+0)+(4+1) {
		t.Fatalf("got %d", got)
	}
}

func TestUnit_EstimateOutputTokens(t *testing.T) {
	t.Parallel()
	if got := estimateOutputTokens(0); got != budgetDefaultOutputTokens {
		t.Fatalf("default: got %d", got)
	}
	if got := estimateOutputTokens(128); got != 128 {
		t.Fatalf("explicit: got %d", got)
	}
}

func TestUnit_EstimateAdmissionCents(t *testing.T) {
	t.Parallel()
	if _, ok := estimateAdmissionCents(estimateAdmissionInput{
		card: billing.CardVersion{}, provider: "mock", model: "mock-1",
		messages: admissionMessages(), maxTokens: 16,
	}); ok {
		t.Fatal("expected failure without a rate card")
	}
	cents, ok := estimateAdmissionCents(estimateAdmissionInput{
		card: admissionCard(), provider: "mock", model: "mock-1",
		messages: admissionMessages(), maxTokens: 16,
	})
	if !ok || cents <= 0 {
		t.Fatalf("cents=%d ok=%v", cents, ok)
	}
}

func TestUnit_BudgetFinalAmount_PrefersMeasuredUsage(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{estimatedCents: 42, card: admissionCard()}
	amount, completeness := budgetFinalAmount(res, "mock", "mock-1", &provider.Usage{InputTokens: 100, OutputTokens: 50})
	if completeness != budgetledger.CompletenessComplete {
		t.Fatalf("completeness=%s", completeness)
	}
	if amount <= 0 || amount == res.estimatedCents {
		t.Fatalf("amount=%d want measured", amount)
	}
}

func TestUnit_BudgetFinalAmount_FallsBackToEstimate(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{estimatedCents: 42, card: admissionCard()}
	for _, usage := range []*provider.Usage{nil, {}} {
		amount, completeness := budgetFinalAmount(res, "mock", "mock-1", usage)
		if amount != res.estimatedCents || completeness != budgetledger.CompletenessEstimated {
			t.Fatalf("usage=%v amount=%d completeness=%s", usage, amount, completeness)
		}
	}
	noPrice := &budgetReservation{estimatedCents: 7, card: billing.CardVersion{Version: "1"}}
	amount, completeness := budgetFinalAmount(noPrice, "mock", "mock-1", &provider.Usage{InputTokens: 1, OutputTokens: 1})
	if amount != 7 || completeness != budgetledger.CompletenessEstimated {
		t.Fatalf("no price: amount=%d completeness=%s", amount, completeness)
	}
}

func TestClaimBudgetAdmission_NoCapSkipsLedger(t *testing.T) {
	t.Parallel()
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{HasHardCap: false})
	r := budgetRequest(uuid.New(), uuid.New())
	out, ok := h.claimBudgetAdmission(httptest.NewRecorder(), r, mockAdmissionInput(0))
	if !ok || len(ledger.claims) != 0 {
		t.Fatalf("ok=%v claims=%d want skip", ok, len(ledger.claims))
	}
	if budgetReservationFromContext(out.Context()) != nil {
		t.Fatal("no reservation expected without a hard cap")
	}
}

func TestClaimBudgetAdmission_OwnedStoresReservation(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	owned := budgetledger.Reservation{ID: uuid.New(), Key: "chat:req-123", Version: 1}
	ledger := &fakeBudgetLedger{claimOut: budgetledger.ClaimOutcome{Kind: budgetledger.ClaimOwned, Reservation: owned}}
	h := admissionHandler(t, ledger, hardCapSnapshot(admissionCard()))
	r := budgetRequest(org, agent)
	out, ok := h.claimBudgetAdmission(httptest.NewRecorder(), r, mockAdmissionInput(32))
	if !ok {
		t.Fatal("expected admission")
	}
	assertAdmissionClaimRecorded(t, ledger, org, agent)
	assertAdmissionReservationStored(t, out, owned)
}

func assertAdmissionClaimRecorded(t *testing.T, ledger *fakeBudgetLedger, org, agent uuid.UUID) {
	t.Helper()
	if len(ledger.claims) != 1 {
		t.Fatalf("claims=%+v", ledger.claims)
	}
	if ledger.claims[0].Key != "chat:req-123" {
		t.Fatalf("key=%q", ledger.claims[0].Key)
	}
	if ledger.claims[0].EstimatedCents <= 0 {
		t.Fatalf("estimate=%d", ledger.claims[0].EstimatedCents)
	}
	if ledger.principals[0].OrgID != org {
		t.Fatalf("principal org=%s", ledger.principals[0].OrgID)
	}
	if ledger.principals[0].AgentID != agent {
		t.Fatalf("principal agent=%s", ledger.principals[0].AgentID)
	}
}

func assertAdmissionReservationStored(t *testing.T, out *http.Request, owned budgetledger.Reservation) {
	t.Helper()
	res := budgetReservationFromContext(out.Context())
	if res == nil {
		t.Fatal("reservation missing")
	}
	if res.claim.ID != owned.ID {
		t.Fatalf("claim id=%s", res.claim.ID)
	}
	if res.settled {
		t.Fatal("fresh reservation must be unsettled")
	}
}

func TestClaimBudgetAdmission_FailClosedOutcomes(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name       string
		snap       billing.BudgetSnapshot
		ledger     *fakeBudgetLedger
		wantStatus int
		wantCode   string
		wantClaims int
	}{
		{
			name:   "cap without rate card",
			snap:   hardCapSnapshot(billing.CardVersion{}),
			ledger: &fakeBudgetLedger{}, wantStatus: http.StatusServiceUnavailable,
			wantCode: "BUDGET_UNAVAILABLE",
		},
		{
			name:   "ledger error",
			snap:   hardCapSnapshot(admissionCard()),
			ledger: &fakeBudgetLedger{claimErr: errors.New("db down")}, wantStatus: http.StatusServiceUnavailable,
			wantCode: "BUDGET_UNAVAILABLE", wantClaims: 1,
		},
		{
			name: "exceeded",
			snap: hardCapSnapshot(admissionCard()),
			ledger: &fakeBudgetLedger{claimOut: budgetledger.ClaimOutcome{
				Kind: budgetledger.ClaimExceeded, RemainingCents: 0,
			}}, wantStatus: http.StatusPaymentRequired, wantCode: "BUDGET_EXCEEDED", wantClaims: 1,
		},
		{
			name: "in progress",
			snap: hardCapSnapshot(admissionCard()),
			ledger: &fakeBudgetLedger{claimOut: budgetledger.ClaimOutcome{
				Kind: budgetledger.ClaimInProgress, RetryAfter: 0,
			}}, wantStatus: http.StatusServiceUnavailable, wantCode: "BUDGET_UNAVAILABLE", wantClaims: 1,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			h := admissionHandler(t, tc.ledger, tc.snap)
			rr := httptest.NewRecorder()
			_, ok := h.claimBudgetAdmission(rr, budgetRequest(uuid.New(), uuid.New()), mockAdmissionInput(0))
			if ok {
				t.Fatal("expected refusal")
			}
			if rr.Code != tc.wantStatus || !strings.Contains(rr.Body.String(), tc.wantCode) {
				t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
			}
			if got := len(tc.ledger.claims); got != tc.wantClaims {
				t.Fatalf("claims=%d want %d", got, tc.wantClaims)
			}
		})
	}
}

func TestSettleBudgetOutcome_FinalizesAndIgnoresRepeats(t *testing.T) {
	t.Parallel()
	claim := budgetledger.Reservation{ID: uuid.New(), Key: "chat:req-123", Version: 2}
	res := &budgetReservation{claim: claim, estimatedCents: 30, card: admissionCard()}
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	ctx := withBudgetReservation(context.Background(), res)
	usage := &provider.Usage{InputTokens: 10, OutputTokens: 5}
	settleSuccess(ctx, h, usage)
	settleSuccess(ctx, h, usage)
	if len(ledger.finalized) != 1 {
		t.Fatalf("finalized=%d want 1", len(ledger.finalized))
	}
	got := ledger.finalized[0]
	if got.claim != claim || got.completeness != budgetledger.CompletenessComplete {
		t.Fatalf("finalize=%+v", got)
	}
	if len(ledger.releases) != 0 {
		t.Fatalf("releases=%d want 0", len(ledger.releases))
	}
}

func TestSettleBudgetOutcome_TransientStatusReleases(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5}
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	ctx := withBudgetReservation(context.Background(), res)
	h.settleBudgetOutcome(ctx, budgetSettlement{status: http.StatusBadGateway, provider: "mock", model: "mock-1"})
	if len(ledger.finalized) != 0 || len(ledger.releases) != 1 {
		t.Fatalf("finalized=%d releases=%d", len(ledger.finalized), len(ledger.releases))
	}
}

func TestReleaseBudget_DropsHoldOnce(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5}
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	ctx := withBudgetReservation(context.Background(), res)
	h.releaseBudget(ctx, "canceled")
	h.releaseBudget(ctx, "provider_failure")
	if len(ledger.releases) != 1 {
		t.Fatalf("releases=%d want 1", len(ledger.releases))
	}
}

func TestSettleBudgetOutcome_FinalizeFailureIsLoggedNotPanicked(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5, card: admissionCard()}
	ledger := &fakeBudgetLedger{finalizeErr: errors.New("db down")}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	h.log = logger.Discard("proxy")
	ctx := withBudgetReservation(context.Background(), res)
	settleSuccess(ctx, h, &provider.Usage{InputTokens: 1, OutputTokens: 1})
	if len(ledger.finalized) != 1 || len(ledger.releases) != 0 {
		t.Fatalf("finalized=%d releases=%d", len(ledger.finalized), len(ledger.releases))
	}
}

func TestClaimBudgetAdmission_MissingIdentityFailsClosed(t *testing.T) {
	t.Parallel()
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, hardCapSnapshot(admissionCard()))
	rr := httptest.NewRecorder()
	bare := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	if _, ok := h.claimBudgetAdmission(rr, bare, mockAdmissionInput(0)); ok {
		t.Fatal("expected refusal")
	}
	if rr.Code != http.StatusServiceUnavailable || !strings.Contains(rr.Body.String(), budgetMissingTenantDetail) {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if len(ledger.claims) != 0 {
		t.Fatalf("claims=%d want 0", len(ledger.claims))
	}
}

func TestClaimBudgetAdmission_MissingRequestIDFailsClosed(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	ctx := auth.WithContext(context.Background(), &auth.ValidateResult{OrgID: org, AgentID: agent})
	ctx = WithAgent(ctx, auth.AgentRecord{ID: agent, OrgID: org, Status: "active"})
	r := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil).WithContext(ctx)
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, hardCapSnapshot(admissionCard()))
	rr := httptest.NewRecorder()
	if _, ok := h.claimBudgetAdmission(rr, r, mockAdmissionInput(0)); ok {
		t.Fatal("expected refusal")
	}
	if rr.Code != http.StatusServiceUnavailable || !strings.Contains(rr.Body.String(), budgetMissingRequestDetail) {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if len(ledger.claims) != 0 {
		t.Fatalf("claims=%d want 0", len(ledger.claims))
	}
}

func TestClaimBudgetAdmission_SnapshotErrorFailsClosed(t *testing.T) {
	t.Parallel()
	h := chatCompletionHandler{
		metrics:      metrics.NewProxy("proxy-test"),
		docsBase:     "https://docs.example.com",
		budgetCache:  newBudgetCache(t, stubBudgetLoader{err: errors.New("billing down")}),
		budgetLedger: &fakeBudgetLedger{},
	}
	rr := httptest.NewRecorder()
	if _, ok := h.claimBudgetAdmission(rr, budgetRequest(uuid.New(), uuid.New()), mockAdmissionInput(0)); ok {
		t.Fatal("expected refusal")
	}
	if rr.Code != http.StatusServiceUnavailable || !strings.Contains(rr.Body.String(), budgetStateDetail) {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestClaimBudgetAdmission_ClaimErrorIsLoggedAndRefused(t *testing.T) {
	t.Parallel()
	ledger := &fakeBudgetLedger{claimErr: errors.New("db down")}
	h := admissionHandler(t, ledger, hardCapSnapshot(admissionCard()))
	h.log = logger.Discard("proxy")
	rr := httptest.NewRecorder()
	if _, ok := h.claimBudgetAdmission(rr, budgetRequest(uuid.New(), uuid.New()), mockAdmissionInput(0)); ok {
		t.Fatal("expected refusal")
	}
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if len(ledger.claims) != 1 {
		t.Fatalf("claims=%d want 1", len(ledger.claims))
	}
}

func TestApplyBudgetClaim_KindMapping(t *testing.T) {
	t.Parallel()
	h := admissionHandler(t, &fakeBudgetLedger{}, billing.BudgetSnapshot{})
	org, agent := uuid.New(), uuid.New()
	cases := []struct {
		name       string
		out        budgetledger.ClaimOutcome
		wantStatus int
		wantHeader string
		wantOK     bool
	}{
		{
			name: "no cap", out: budgetledger.ClaimOutcome{Kind: budgetledger.ClaimNoCap},
			wantStatus: http.StatusOK, wantOK: true,
		},
		{
			name: "conflict", out: budgetledger.ClaimOutcome{Kind: budgetledger.ClaimConflict},
			wantStatus: http.StatusServiceUnavailable,
		},
		{
			name:       "in progress honors retry-after",
			out:        budgetledger.ClaimOutcome{Kind: budgetledger.ClaimInProgress, RetryAfter: 90 * time.Second},
			wantStatus: http.StatusServiceUnavailable, wantHeader: "91",
		},
		{
			name: "unknown kind", out: budgetledger.ClaimOutcome{Kind: budgetledger.ClaimKind("weird")},
			wantStatus: http.StatusServiceUnavailable,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rr := httptest.NewRecorder()
			_, ok := h.applyBudgetClaim(budgetRequest(org, agent), rr, budgetApproval{out: tc.out})
			if ok != tc.wantOK {
				t.Fatalf("ok=%v want %v", ok, tc.wantOK)
			}
			if tc.wantStatus != http.StatusOK && rr.Code != tc.wantStatus {
				t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
			}
			if tc.wantHeader != "" && rr.Header().Get("Retry-After") != tc.wantHeader {
				t.Fatalf("retry-after=%q want %q", rr.Header().Get("Retry-After"), tc.wantHeader)
			}
		})
	}
}

func TestRebudgetForFallback_MissingIdentityRefuses(t *testing.T) {
	t.Parallel()
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5, card: admissionCard()}
	r := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	r = r.WithContext(withBudgetReservation(r.Context(), res))
	if _, ok := h.rebudgetForFallback(r, mockAdmissionInput(64)); ok {
		t.Fatal("expected refusal")
	}
	if len(ledger.claims) != 0 || len(ledger.releases) != 0 {
		t.Fatalf("claims=%d releases=%d", len(ledger.claims), len(ledger.releases))
	}
}

func TestSettleBudgetOutcome_EstimatedWithoutUsage(t *testing.T) {
	t.Parallel()
	claim := budgetledger.Reservation{ID: uuid.New(), Version: 1}
	res := &budgetReservation{claim: claim, estimatedCents: 42, card: admissionCard()}
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	settleSuccess(withBudgetReservation(context.Background(), res), h, nil)
	if len(ledger.finalized) != 1 || len(ledger.releases) != 0 {
		t.Fatalf("finalized=%d releases=%d", len(ledger.finalized), len(ledger.releases))
	}
	got := ledger.finalized[0]
	if got.cents != 42 || got.completeness != budgetledger.CompletenessEstimated {
		t.Fatalf("finalize=%+v", got)
	}
}

func TestReleaseBudget_ErrorIsLoggedNotPanicked(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5}
	ledger := &fakeBudgetLedger{releaseErr: errors.New("db down")}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	h.log = logger.Discard("proxy")
	h.releaseBudget(withBudgetReservation(context.Background(), res), "canceled")
	if len(ledger.releases) != 1 {
		t.Fatalf("releases=%d want 1", len(ledger.releases))
	}
}

func TestUnit_HandlePrimaryCompleteError_CanceledReleasesHold(t *testing.T) {
	t.Parallel()
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5}
	h.handlePrimaryCompleteError(primaryCompleteErrorArgs{
		p:       chatForwardParams{r: reservationRequest(t, res)},
		provReq: provider.Request{Model: "mock-1"},
		err:     context.Canceled,
	})
	if len(ledger.releases) != 1 {
		t.Fatalf("releases=%d want 1 (canceled request drops the hold)", len(ledger.releases))
	}
	if len(ledger.finalized) != 0 {
		t.Fatalf("finalized=%d want 0", len(ledger.finalized))
	}
}

func reservationRequest(t *testing.T, res *budgetReservation) *http.Request {
	t.Helper()
	r := budgetRequest(uuid.New(), uuid.New())
	return r.WithContext(withBudgetReservation(r.Context(), res))
}

func TestRebudgetForFallback_RepricesHold(t *testing.T) {
	t.Parallel()
	primary := budgetledger.Reservation{ID: uuid.New(), Key: "chat:req-123", Version: 1}
	next := budgetledger.Reservation{ID: uuid.New(), Key: "chat:req-123", Version: 1}
	ledger := &fakeBudgetLedger{claimOut: budgetledger.ClaimOutcome{Kind: budgetledger.ClaimOwned, Reservation: next}}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	r := reservationRequest(t, &budgetReservation{claim: primary, estimatedCents: 5, card: admissionCard()})
	out, ok := h.rebudgetForFallback(r, mockAdmissionInput(64))
	if !ok {
		t.Fatal("expected reprice")
	}
	if len(ledger.releases) != 1 || ledger.releases[0] != primary {
		t.Fatalf("releases=%+v", ledger.releases)
	}
	if len(ledger.claims) != 1 || ledger.claims[0].Key != "chat:req-123" || ledger.claims[0].EstimatedCents <= 0 {
		t.Fatalf("claims=%+v", ledger.claims)
	}
	res := budgetReservationFromContext(out.Context())
	if res == nil || res.claim.ID != next.ID || res.settled {
		t.Fatalf("reservation=%+v", res)
	}
}

func TestRebudgetForFallback_FailsClosed(t *testing.T) {
	t.Parallel()
	primary := budgetledger.Reservation{ID: uuid.New(), Key: "chat:req-123", Version: 1}
	cases := []struct {
		name         string
		card         billing.CardVersion
		ledger       *fakeBudgetLedger
		wantClaims   int
		wantReleases int
	}{
		{
			name: "no price for fallback model", card: billing.CardVersion{Version: "1"},
			ledger: &fakeBudgetLedger{}, wantClaims: 0, wantReleases: 0,
		},
		{
			name: "exceeded", card: admissionCard(),
			ledger:     &fakeBudgetLedger{claimOut: budgetledger.ClaimOutcome{Kind: budgetledger.ClaimExceeded}},
			wantClaims: 1, wantReleases: 1,
		},
		{
			name: "ledger error", card: admissionCard(),
			ledger:     &fakeBudgetLedger{claimErr: errors.New("db down")},
			wantClaims: 1, wantReleases: 1,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			h := admissionHandler(t, tc.ledger, billing.BudgetSnapshot{})
			r := reservationRequest(t, &budgetReservation{claim: primary, estimatedCents: 5, card: tc.card})
			if _, ok := h.rebudgetForFallback(r, mockAdmissionInput(64)); ok {
				t.Fatal("expected refusal")
			}
			if len(tc.ledger.claims) != tc.wantClaims {
				t.Fatalf("claims=%d want %d", len(tc.ledger.claims), tc.wantClaims)
			}
			if len(tc.ledger.releases) != tc.wantReleases {
				t.Fatalf("releases=%d want %d", len(tc.ledger.releases), tc.wantReleases)
			}
		})
	}
}

func TestRebudgetForFallback_PassthroughWithoutHoldOrLedger(t *testing.T) {
	t.Parallel()
	h := admissionHandler(t, &fakeBudgetLedger{}, billing.BudgetSnapshot{})
	r := budgetRequest(uuid.New(), uuid.New())
	out, ok := h.rebudgetForFallback(r, mockAdmissionInput(0))
	if !ok || out != r {
		t.Fatal("expected passthrough without a hold")
	}
	r = reservationRequest(t, &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New()}, card: admissionCard()})
	noLedger := admissionHandler(t, nil, billing.BudgetSnapshot{})
	out, ok = noLedger.rebudgetForFallback(r, mockAdmissionInput(0))
	if !ok || out != r {
		t.Fatal("expected passthrough without a ledger")
	}
}

func TestStreamCheckpointHook_IncompleteSettlesMeasuredUsage(t *testing.T) {
	t.Parallel()
	res := &budgetReservation{claim: budgetledger.Reservation{ID: uuid.New(), Version: 1}, estimatedCents: 5, card: admissionCard()}
	ledger := &fakeBudgetLedger{}
	h := admissionHandler(t, ledger, billing.BudgetSnapshot{})
	r := reservationRequest(t, res)
	hook := h.streamCheckpointHook(r, &llm.ChatCompletionRequest{Model: "mock-1"}, "mock", fallbackAudit{})
	hook(r.Context(), streamCheckpointResult{complete: false, usage: &provider.Usage{InputTokens: 10, OutputTokens: 5}})
	if len(ledger.finalized) != 1 || len(ledger.releases) != 0 {
		t.Fatalf("finalized=%d releases=%d", len(ledger.finalized), len(ledger.releases))
	}
	if ledger.finalized[0].completeness != budgetledger.CompletenessComplete {
		t.Fatalf("completeness=%s", ledger.finalized[0].completeness)
	}
}

func TestBudgetReservationKey_RequiresRequestID(t *testing.T) {
	t.Parallel()
	if got := budgetReservationKey(context.Background()); got != "" {
		t.Fatalf("got %q want empty", got)
	}
	ctx := WithRequestID(context.Background(), "abc")
	if got := budgetReservationKey(ctx); got != "chat:abc" {
		t.Fatalf("got %q", got)
	}
}

func TestUnit_MaxTokensFromParsed(t *testing.T) {
	t.Parallel()
	if got := maxTokensFromParsed(nil); got != 0 {
		t.Fatalf("nil parsed: %d", got)
	}
	explicit := 64
	if got := maxTokensFromParsed(&llm.ChatCompletionRequest{MaxTokens: &explicit}); got != 64 {
		t.Fatalf("explicit parsed: %d", got)
	}
}
