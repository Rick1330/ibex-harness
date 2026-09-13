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
	return h.walkFallbackChain(p, primaryReq, orgID, chain, reason)
}

func (h chatCompletionHandler) walkFallbackChain(
	p chatForwardParams,
	primaryReq provider.Request,
	orgID uuid.UUID,
	chain []string,
	reason string,
) (fallbackSuccess, bool) {
	for _, hopModel := range chain {
		if errors.Is(p.r.Context().Err(), context.Canceled) {
			return fallbackSuccess{}, false
		}
		hopProv, err := h.modelRouter.ForOrg(p.r.Context(), orgID, hopModel)
		if err != nil {
			if errors.Is(err, modelpolicy.ErrPolicyUnavailable) {
				return fallbackSuccess{}, false
			}
			if errors.Is(err, modelpolicy.ErrModelNotAllowedForOrg) ||
				errors.Is(err, provider.ErrNoProviderForModel) {
				continue
			}
			continue
		}
		hopReq := primaryReq
		hopReq.Model = hopModel
		hopReq.APIKeyOverride = ""
		hopReq.BaseURLOverride = ""
		start := time.Now()
		resp, err := hopProv.Complete(p.r.Context(), hopReq)
		elapsed := time.Since(start)
		if h.metrics != nil {
			h.metrics.ObserveProviderDurationSeconds(hopProv.Name(), elapsed.Seconds())
		}
		if err != nil {
			if errors.Is(err, context.Canceled) {
				return fallbackSuccess{}, false
			}
			continue
		}
		return fallbackSuccess{prov: hopProv, resp: resp, model: hopModel, reason: reason}, true
	}
	return fallbackSuccess{}, false
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
