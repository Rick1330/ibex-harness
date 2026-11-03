package http

import (
	"context"
	"fmt"
	"net/http"
	"time"
	"unicode/utf8"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/budgetledger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/http/chat"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

const (
	// budgetAdmissionTimeout bounds the claim transaction on the request path.
	budgetAdmissionTimeout = 2 * time.Second
	// budgetSettleTimeout bounds detached finalize/release after the response.
	budgetSettleTimeout = 5 * time.Second
	// budgetDefaultOutputTokens bounds output cost when max_tokens is unset.
	budgetDefaultOutputTokens = 4096
	// budgetTokensPerMessage approximates per-message framing overhead.
	budgetTokensPerMessage = 4
	// budgetBytesPerToken converts UTF-8 bytes to a rough token count.
	budgetBytesPerToken = 4

	budgetUnavailableMessage   = "Budget enforcement unavailable"
	budgetExceededMessage      = "Budget exceeded for this organization"
	budgetInProgressDetail     = "budget admission for this request is still in progress"
	budgetExceededDetail       = "durable reservation would exceed the active hard-cap period"
	budgetMissingTenantDetail  = "missing tenant identity for budget admission"
	budgetMissingRequestDetail = "missing request identity for budget admission"
	budgetStateDetail          = "budget state unavailable"
	budgetEstimateDetail       = "no published rate card for this provider/model"
	budgetClaimDetail          = "durable reservation claim failed"
	budgetConflictDetail       = "durable reservation conflict"
)

// budgetReservation tracks one owned admission hold. Settlement happens on the
// same request goroutine as the claim, so the settled flag needs no lock.
type budgetReservation struct {
	claim          budgetledger.Reservation
	estimatedCents int64
	card           billing.CardVersion
	settled        bool
}

// budgetAdmissionInput carries the priced request shape for admission.
type budgetAdmissionInput struct {
	provider  string
	model     string
	messages  []provider.Message
	maxTokens int
}

// budgetSettlement carries the post-provider outcome for the owned hold.
type budgetSettlement struct {
	status   int
	provider string
	model    string
	usage    *provider.Usage
}

// claimBudgetAdmission takes a durable hard-cap hold before the provider call.
// Orgs without an active hard_cap period keep the cache-only middleware path.
// On false a fail-closed response has already been written.
func (h chatCompletionHandler) claimBudgetAdmission(
	w http.ResponseWriter,
	r *http.Request,
	in budgetAdmissionInput,
) (*http.Request, bool) {
	if h.budgetLedger == nil || h.budgetCache == nil {
		return r, true
	}
	principal, key, invalidDetail := budgetAdmissionIDs(r)
	if invalidDetail != "" {
		h.writeBudgetAdmissionUnavailable(w, r, invalidDetail)
		return r, false
	}
	snap, err := h.budgetCache.SnapshotForOrg(r.Context(), principal.OrgID)
	if err != nil {
		h.writeBudgetAdmissionUnavailable(w, r, budgetStateDetail)
		return r, false
	}
	if !snap.HasHardCap {
		h.metrics.IncBudgetReservation(metrics.BudgetReservationNoCap)
		return r, true
	}
	estimate, ok := estimateAdmissionCents(estimateAdmissionInput{
		card: snap.PublishedCard, provider: in.provider, model: in.model,
		messages: in.messages, maxTokens: in.maxTokens,
	})
	if !ok {
		h.writeBudgetAdmissionUnavailable(w, r, budgetEstimateDetail)
		return r, false
	}
	out, ok := h.claimDurableHold(r, budgetledger.ClaimRequest{
		Key: key, RequestHash: budgetledger.HashRequest([]byte(key)), EstimatedCents: estimate,
	}, principal, w)
	if !ok {
		return r, false
	}
	return h.applyBudgetClaim(r, w, budgetApproval{out: out, estimate: estimate, snap: snap})
}

// budgetApproval bundles one successful claim call with its pricing context.
type budgetApproval struct {
	out      budgetledger.ClaimOutcome
	estimate int64
	snap     billing.BudgetSnapshot
}

// budgetAdmissionIDs resolves the tenant principal and reservation key; a
// non-empty detail means the response was already refused.
func budgetAdmissionIDs(r *http.Request) (budgetledger.Principal, string, string) {
	orgID, agentID, ok := tenantIDsFromContext(r.Context())
	if !ok {
		return budgetledger.Principal{}, "", budgetMissingTenantDetail
	}
	key := budgetReservationKey(r.Context())
	if key == "" {
		return budgetledger.Principal{}, "", budgetMissingRequestDetail
	}
	return budgetledger.Principal{OrgID: orgID, AgentID: agentID}, key, ""
}

// claimHoldTimed runs one bounded ledger claim and records its latency.
func (h chatCompletionHandler) claimHoldTimed(
	ctx context.Context,
	p budgetledger.Principal,
	req budgetledger.ClaimRequest,
) (budgetledger.ClaimOutcome, error) {
	claimCtx, cancel := context.WithTimeout(ctx, budgetAdmissionTimeout)
	defer cancel()
	start := time.Now()
	out, err := h.budgetLedger.Claim(claimCtx, p, req)
	h.metrics.ObserveBudgetReservationDurationSeconds(time.Since(start).Seconds())
	return out, err
}

// claimDurableHold runs the timed claim call and logs failures. ok=false means
// the caller must stop; the error response is written here.
func (h chatCompletionHandler) claimDurableHold(
	r *http.Request,
	req budgetledger.ClaimRequest,
	p budgetledger.Principal,
	w http.ResponseWriter,
) (budgetledger.ClaimOutcome, bool) {
	out, err := h.claimHoldTimed(r.Context(), p, req)
	if err != nil {
		h.metrics.IncBudgetReservation(metrics.BudgetReservationUnavailable)
		if h.log != nil {
			h.log.WarnCtx(r.Context(), "budget reservation claim failed; failing closed",
				"org_id", p.OrgID.String(), "error", err)
		}
		h.writeBudgetAdmissionUnavailable(w, r, budgetClaimDetail)
		return budgetledger.ClaimOutcome{}, false
	}
	return out, true
}

// budgetClaimMetric maps a claim kind onto its reservation outcome series.
func budgetClaimMetric(kind budgetledger.ClaimKind) string {
	switch kind {
	case budgetledger.ClaimOwned:
		return metrics.BudgetReservationClaimed
	case budgetledger.ClaimNoCap:
		return metrics.BudgetReservationNoCap
	case budgetledger.ClaimExceeded:
		return metrics.BudgetReservationExceeded
	case budgetledger.ClaimInProgress:
		return metrics.BudgetReservationInProgress
	case budgetledger.ClaimConflict:
		return metrics.BudgetReservationConflict
	default:
		return metrics.BudgetReservationUnavailable
	}
}

// applyBudgetClaim maps the typed claim outcome onto the request or an error.
func (h chatCompletionHandler) applyBudgetClaim(
	r *http.Request,
	w http.ResponseWriter,
	in budgetApproval,
) (*http.Request, bool) {
	h.metrics.IncBudgetReservation(budgetClaimMetric(in.out.Kind))
	switch in.out.Kind {
	case budgetledger.ClaimOwned:
		res := &budgetReservation{
			claim: in.out.Reservation, estimatedCents: in.estimate, card: in.snap.PublishedCard,
		}
		return r.WithContext(withBudgetReservation(r.Context(), res)), true
	case budgetledger.ClaimNoCap:
		return r, true
	case budgetledger.ClaimExceeded:
		h.metrics.IncBudgetDeny()
		h.writeBudgetExceeded(w, r, in.out.RemainingCents)
		return r, false
	case budgetledger.ClaimInProgress:
		if in.out.RetryAfter > 0 {
			w.Header().Set("Retry-After", fmt.Sprintf("%d", int(in.out.RetryAfter.Seconds())+1))
		}
		h.writeBudgetAdmissionUnavailable(w, r, budgetInProgressDetail)
		return r, false
	case budgetledger.ClaimConflict:
		h.writeBudgetAdmissionUnavailable(w, r, budgetConflictDetail)
		return r, false
	default:
		h.writeBudgetAdmissionUnavailable(w, r, budgetClaimDetail)
		return r, false
	}
}

// rebudgetForFallback replaces the primary hold with one priced for the
// fallback model before the hop runs. ok=false means the fallback must be
// skipped (fail closed); no response is written because the primary provider
// failure still surfaces to the client.
func (h chatCompletionHandler) rebudgetForFallback(
	r *http.Request,
	in budgetAdmissionInput,
) (*http.Request, bool) {
	res := budgetReservationFromContext(r.Context())
	if res == nil || h.budgetLedger == nil {
		return r, true
	}
	principal, key, invalidDetail := budgetAdmissionIDs(r)
	if invalidDetail != "" {
		return r, false
	}
	estimate, ok := estimateAdmissionCents(estimateAdmissionInput{
		card: res.card, provider: in.provider, model: in.model,
		messages: in.messages, maxTokens: in.maxTokens,
	})
	if !ok {
		return r, false
	}
	h.releaseBudget(r.Context(), "fallback_reprice")
	out, err := h.claimHoldTimed(r.Context(), principal, budgetledger.ClaimRequest{
		Key: key, RequestHash: budgetledger.HashRequest([]byte(key)), EstimatedCents: estimate,
	})
	if err != nil {
		h.metrics.IncBudgetReservation(metrics.BudgetReservationUnavailable)
		return r, false
	}
	h.metrics.IncBudgetReservation(budgetClaimMetric(out.Kind))
	if out.Kind == budgetledger.ClaimExceeded {
		h.metrics.IncBudgetDeny()
	}
	if out.Kind != budgetledger.ClaimOwned {
		return r, false
	}
	next := &budgetReservation{claim: out.Reservation, estimatedCents: estimate, card: res.card}
	return r.WithContext(withBudgetReservation(r.Context(), next)), true
}

// settleBudgetOutcome finalizes the hold after a completed provider call.
// Transient statuses (429/5xx) release so a retry can fit, mirroring the
// idempotency commit rules.
func (h chatCompletionHandler) settleBudgetOutcome(ctx context.Context, in budgetSettlement) {
	res := budgetReservationFromContext(ctx)
	if res == nil || res.settled {
		return
	}
	res.settled = true
	if !chat.ShouldCommit(in.status) {
		h.releaseReservation(ctx, res, "transient_status")
		return
	}
	amount, completeness := budgetFinalAmount(res, in.provider, in.model, in.usage)
	opCtx, cancel := budgetOpContext(ctx)
	defer cancel()
	if err := h.budgetLedger.Finalize(opCtx, res.claim, amount, completeness); err != nil {
		h.metrics.IncBudgetReservation(metrics.BudgetReservationFinalizeFailed)
		if h.log != nil {
			h.log.WarnCtx(opCtx, "budget reservation finalize failed",
				"org_id", res.claim.Principal.OrgID.String(), "error", err)
		}
		return
	}
	if completeness == budgetledger.CompletenessComplete {
		h.metrics.IncBudgetReservation(metrics.BudgetReservationFinalizedComplete)
		return
	}
	h.metrics.IncBudgetReservation(metrics.BudgetReservationFinalizedEstimated)
}

// releaseBudget drops an unsettled hold on any pre-success exit path.
func (h chatCompletionHandler) releaseBudget(ctx context.Context, reason string) {
	res := budgetReservationFromContext(ctx)
	if res == nil || res.settled {
		return
	}
	res.settled = true
	h.releaseReservation(ctx, res, reason)
}

func (h chatCompletionHandler) releaseReservation(ctx context.Context, res *budgetReservation, reason string) {
	opCtx, cancel := budgetOpContext(ctx)
	defer cancel()
	if err := h.budgetLedger.Release(opCtx, res.claim); err != nil {
		h.metrics.IncBudgetReservation(metrics.BudgetReservationReleaseFailed)
		if h.log != nil {
			h.log.WarnCtx(opCtx, "budget reservation release failed; lease will expire",
				"org_id", res.claim.Principal.OrgID.String(), "reason", reason, "error", err)
		}
		return
	}
	h.metrics.IncBudgetReservation(metrics.BudgetReservationReleased)
}

// budgetFinalAmount prefers measured usage; a provider without usage settles at
// the admission estimate with an explicit estimated marker.
func budgetFinalAmount(res *budgetReservation, providerName, model string, usage *provider.Usage) (int64, budgetledger.Completeness) {
	if !hasMeasuredUsage(usage) {
		return res.estimatedCents, budgetledger.CompletenessEstimated
	}
	cents, _, ok := estimateCostChecked(estimateCostInput{
		card: res.card, provider: providerName, model: model,
		inTok: int64(usage.InputTokens), outTok: int64(usage.OutputTokens),
	})
	if !ok {
		return res.estimatedCents, budgetledger.CompletenessEstimated
	}
	return cents, budgetledger.CompletenessComplete
}

// hasMeasuredUsage reports whether the provider returned any usable tokens.
func hasMeasuredUsage(usage *provider.Usage) bool {
	if usage == nil {
		return false
	}
	return usage.InputTokens > 0 || usage.OutputTokens > 0
}

// budgetOpContext detaches settlement from request cancellation: the response
// is already written, but the ledger transition must complete. Request-scoped
// values (request id, trace context) are preserved for log correlation.
func budgetOpContext(ctx context.Context) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.WithoutCancel(ctx), budgetSettleTimeout)
}

func budgetReservationKey(ctx context.Context) string {
	requestID := requestIDFromContext(ctx)
	if requestID == "" {
		return ""
	}
	return "chat:" + requestID
}

type estimateAdmissionInput struct {
	card      billing.CardVersion
	provider  string
	model     string
	messages  []provider.Message
	maxTokens int
}

func estimateAdmissionCents(in estimateAdmissionInput) (int64, bool) {
	cents, _, ok := estimateCostChecked(estimateCostInput{
		card: in.card, provider: in.provider, model: in.model,
		inTok: estimateInputTokens(in.messages), outTok: estimateOutputTokens(in.maxTokens),
	})
	return cents, ok
}

// estimateInputTokens approximates prompt tokens without a tokenizer: per
// message take max(runes, bytes/4) plus framing overhead.
func estimateInputTokens(messages []provider.Message) int64 {
	var total int64
	for _, m := range messages {
		total += budgetTokensPerMessage + messageTokenHeuristic(m.Content)
	}
	return total
}

func messageTokenHeuristic(content string) int64 {
	if content == "" {
		return 0
	}
	byBytes := int64(len(content) / budgetBytesPerToken)
	byRunes := int64(utf8.RuneCountInString(content))
	return maxInt64(byBytes, byRunes)
}

func maxTokensFromParsed(parsed *llm.ChatCompletionRequest) int {
	if parsed == nil || parsed.MaxTokens == nil {
		return 0
	}
	return *parsed.MaxTokens
}

func estimateOutputTokens(maxTokens int) int64 {
	if maxTokens > 0 {
		return int64(maxTokens)
	}
	return budgetDefaultOutputTokens
}

func (h chatCompletionHandler) writeBudgetAdmissionUnavailable(w http.ResponseWriter, r *http.Request, detail string) {
	apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeBudgetUnavailable,
		budgetUnavailableMessage, requestIDFromContext(r.Context()),
		apierror.WriteOpts{Detail: detail, DocsBase: h.docsBase})
}

func (h chatCompletionHandler) writeBudgetExceeded(w http.ResponseWriter, r *http.Request, remainingCents int64) {
	apierror.WriteStatus(w, http.StatusPaymentRequired, apierror.CodeBudgetExceeded,
		budgetExceededMessage, requestIDFromContext(r.Context()),
		apierror.WriteOpts{Detail: budgetExceededDetail, DocsBase: h.docsBase})
}
