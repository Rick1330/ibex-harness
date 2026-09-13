package http

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

const (
	headerIBEXProviderFallback = "X-IBEX-Provider-Fallback"
	headerIBEXProviderUsed     = "X-IBEX-Provider-Used"
)

// policyFallbackChain loads org fallback_chain for a model (ADR-0077).
type policyFallbackChain interface {
	FallbackChain(ctx context.Context, orgID uuid.UUID, model string) ([]string, error)
}

type fallbackSuccess struct {
	prov   provider.Provider
	resp   provider.Response
	model  string
	reason string
}

type fallbackAudit struct {
	OriginalModel string
	FallbackModel string
	Reason        string
}

type walkFallbackArgs struct {
	p          chatForwardParams
	primaryReq provider.Request
	orgID      uuid.UUID
	chain      []string
	reason     string
}

type hopResult int

const (
	hopContinue hopResult = iota
	hopAbort
	hopOK
)

func (h chatCompletionHandler) tryFallbackComplete(
	p chatForwardParams,
	primaryReq provider.Request,
	reason string,
) (fallbackSuccess, bool) {
	if h.policyFallback == nil || h.modelRouter == nil {
		return fallbackSuccess{}, false
	}
	orgID, ok := orgUUIDFromAuth(p.r.Context())
	if !ok {
		return fallbackSuccess{}, false
	}
	originalModel := fallbackOriginalModel(primaryReq.Model, p.parsed)
	chain, err := h.policyFallback.FallbackChain(p.r.Context(), orgID, originalModel)
	if err != nil {
		return fallbackSuccess{}, false
	}
	chain = modelpolicy.TruncateChain(chain, h.maxFallbackDepth)
	if len(chain) == 0 {
		return fallbackSuccess{}, false
	}
	return h.walkFallbackChain(walkFallbackArgs{
		p: p, primaryReq: primaryReq, orgID: orgID, chain: chain, reason: reason,
	})
}

func (h chatCompletionHandler) walkFallbackChain(args walkFallbackArgs) (fallbackSuccess, bool) {
	for _, hopModel := range args.chain {
		stop, fb, ok := h.advanceFallbackHop(args, hopModel)
		if stop {
			return fb, ok
		}
	}
	return fallbackSuccess{}, false
}

func (h chatCompletionHandler) advanceFallbackHop(
	args walkFallbackArgs,
	hopModel string,
) (stop bool, fb fallbackSuccess, ok bool) {
	if args.p.r.Context().Err() != nil {
		return true, fallbackSuccess{}, false
	}
	switch outcome, hop := h.tryFallbackHop(args, hopModel); outcome {
	case hopOK:
		return true, hop, true
	case hopAbort:
		return true, fallbackSuccess{}, false
	default:
		return false, fallbackSuccess{}, false
	}
}

func (h chatCompletionHandler) tryFallbackHop(args walkFallbackArgs, hopModel string) (hopResult, fallbackSuccess) {
	hopProv, err := h.resolveFallbackProvider(args, hopModel)
	if err != nil {
		if skipFallbackForOrgErr(err) {
			return hopContinue, fallbackSuccess{}
		}
		return hopAbort, fallbackSuccess{}
	}
	hopReq := fallbackHopRequest(args.primaryReq, hopModel)
	ctx := args.p.r.Context()
	resp, err := h.completeFallbackHop(ctx, hopProv, hopReq)
	if err != nil {
		return classifyFallbackHopErr(ctx, err, hopReq)
	}
	return hopOK, fallbackSuccess{
		prov: hopProv, resp: resp, model: hopModel, reason: args.reason,
	}
}

func (h chatCompletionHandler) resolveFallbackProvider(args walkFallbackArgs, hopModel string) (provider.Provider, error) {
	return h.modelRouter.ForOrg(args.p.r.Context(), args.orgID, hopModel)
}

func skipFallbackForOrgErr(err error) bool {
	return errors.Is(err, modelpolicy.ErrModelNotAllowedForOrg) ||
		errors.Is(err, provider.ErrNoProviderForModel)
}

func fallbackHopRequest(primary provider.Request, hopModel string) provider.Request {
	hopReq := primary
	hopReq.Model = hopModel
	hopReq.APIKeyOverride = ""
	hopReq.BaseURLOverride = ""
	return hopReq
}

func (h chatCompletionHandler) completeFallbackHop(
	ctx context.Context,
	hopProv provider.Provider,
	hopReq provider.Request,
) (provider.Response, error) {
	start := time.Now()
	resp, err := hopProv.Complete(ctx, hopReq)
	if h.metrics != nil {
		h.metrics.ObserveProviderDurationSeconds(hopProv.Name(), time.Since(start).Seconds())
	}
	return resp, err
}

func classifyFallbackHopErr(ctx context.Context, err error, hopReq provider.Request) (hopResult, fallbackSuccess) {
	if ctx.Err() != nil || errors.Is(err, context.Canceled) {
		return hopAbort, fallbackSuccess{}
	}
	if !provider.FallbackEligible(err, hopReq).Eligible {
		return hopAbort, fallbackSuccess{}
	}
	return hopContinue, fallbackSuccess{}
}

func orgUUIDFromAuth(ctx context.Context) (uuid.UUID, bool) {
	authRes, ok := auth.FromContext(ctx)
	if !ok || authRes.OrgID == uuid.Nil {
		return uuid.Nil, false
	}
	return authRes.OrgID, true
}

func fallbackOriginalModel(reqModel string, parsed *llm.ChatCompletionRequest) string {
	if m := strings.TrimSpace(reqModel); m != "" {
		return m
	}
	if parsed == nil {
		return ""
	}
	return strings.TrimSpace(parsed.Model)
}

func setFallbackSuccessHeaders(w http.ResponseWriter, model string) {
	w.Header().Set(headerIBEXProviderFallback, "true")
	w.Header().Set(headerIBEXProviderUsed, model)
}

func (h chatCompletionHandler) acceptFallbackSubstitution(w http.ResponseWriter, audit fallbackAudit) {
	if audit.FallbackModel == "" {
		return
	}
	setFallbackSuccessHeaders(w, audit.FallbackModel)
	if h.metrics != nil {
		h.metrics.IncProviderFallback(audit.Reason)
	}
}

func checkpointModel(parsed *llm.ChatCompletionRequest, audit fallbackAudit) string {
	if audit.FallbackModel != "" {
		return audit.FallbackModel
	}
	if parsed == nil {
		return ""
	}
	return parsed.Model
}
