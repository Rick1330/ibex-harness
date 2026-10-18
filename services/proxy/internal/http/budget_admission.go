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
	"github.com/Rick1330/ibex-harness/packages/reqid"
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

// claimBudgetAdmission takes a durable hard-cap hold before the provider call.
// Orgs without an active hard_cap period keep the cache-only middleware path.
// On false a fail-closed response has already been written.
func (h chatCompletionHandler) claimBudgetAdmission(
	w http.ResponseWriter,
	r *http.Request,
	providerName, model string,
	messages []provider.Message,
	maxTokens int,
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
		card: snap.PublishedCard, provider: providerName, model: model,
		messages: messages, maxTokens: maxTokens,
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
	return h.applyBudgetClaim(r, w, out, estimate, snap)
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

// claimDurableHold runs the timed claim call and logs failures. ok=false means
// the caller must stop; the error response is written here.
func (h chatCompletionHandler) claimDurableHold(
	r *http.Request,
	req budgetledger.ClaimRequest,
	p budgetledger.Principal,
	w http.ResponseWriter,
) (budgetledger.ClaimOutcome, bool) {
	ctx, cancel := context.WithTimeout(r.Context(), budgetAdmissionTimeout)
	defer cancel()
	start := time.Now()
	out, err := h.budgetLedger.Claim(ctx, p, req)
	h.metrics.ObserveBudgetReservationDurationSeconds(time.Since(start).Seconds())
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

// applyBudgetClaim maps the typed claim outcome onto the request or an error.
func (h chatCompletionHandler) applyBudgetClaim(
	r *http.Request,
	w http.ResponseWriter,
	out budgetledger.ClaimOutcome,
	estimate int64,
	snap billing.BudgetSnapshot,
) (*http.Request, bool) {
	switch out.Kind {
	case budgetledger.ClaimOwned:
		h.metrics.IncBudgetReservation(metrics.BudgetReservationClaimed)
		res := &budgetReservation{claim: out.Reservation, estimatedCents: estimate, card: snap.PublishedCard}
		return r.WithContext(withBudgetReservation(r.Context(), res)), true
	case budgetledger.ClaimNoCap:
		h.metrics.IncBudgetReservation(metrics.BudgetReservationNoCap)
		return r, true
	case budgetledger.ClaimExceeded:
		h.metrics.IncBudgetReservation(metrics.BudgetReservationExceeded)
		h.metrics.IncBudgetDeny()
		h.writeBudgetExceeded(w, r, out.RemainingCents)
		return r, false
	case budgetledger.ClaimInProgress:
		h.metrics.IncBudgetReservation(metrics.BudgetReservationInProgress)
		if out.RetryAfter > 0 {
			w.Header().Set("Retry-After", fmt.Sprintf("%d", int(out.RetryAfter.Seconds())+1))
		}
		h.writeBudgetAdmissionUnavailable(w, r, budgetInProgressDetail)
		return r, false
	case budgetledger.ClaimConflict:
		h.metrics.IncBudgetReservation(metrics.BudgetReservationConflict)
		h.writeBudgetAdmissionUnavailable(w, r, budgetConflictDetail)
		return r, false
	default:
		h.metrics.IncBudgetReservation(metrics.BudgetReservationUnavailable)
		h.writeBudgetAdmissionUnavailable(w, r, budgetClaimDetail)
		return r, false
	}
}

// settleBudgetOutcome finalizes the hold after a completed provider call.
// Transient statuses (429/5xx) release so a retry can fit, mirroring the
// idempotency commit rules.
func (h chatCompletionHandler) settleBudgetOutcome(
	ctx context.Context,
	status int,
	providerName, model string,
	usage *provider.Usage,
) {
	res := budgetReservationFromContext(ctx)
	if res == nil || res.settled {
		return
	}
	res.settled = true
	if !chat.ShouldCommit(status) {
		h.releaseReservation(ctx, res, "transient_status")
		return
	}
	amount, completeness := budgetFinalAmount(res, providerName, model, usage)
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
	if usage == nil || (usage.InputTokens <= 0 && usage.OutputTokens <= 0) {
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

// budgetOpContext detaches settlement from the request context: the response is
// already written, but the ledger transition must complete.
func budgetOpContext(ctx context.Context) (context.Context, context.CancelFunc) {
	base := context.Background()
	if id, ok := reqid.FromContext(ctx); ok {
		base = reqid.WithRequestID(base, id)
	}
	return context.WithTimeout(base, budgetSettleTimeout)
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
