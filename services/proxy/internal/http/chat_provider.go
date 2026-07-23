package http

import (
	"context"
	"errors"
	"io"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type chatForwardParams struct {
	w      http.ResponseWriter
	r      *http.Request
	parsed *llm.ChatCompletionRequest
	prov   provider.Provider
}

func (h chatCompletionHandler) forwardChatCompletion(p chatForwardParams) {
	ctx := p.r.Context()
	requestID := requestIDFromContext(ctx)
	if errors.Is(ctx.Err(), context.Canceled) {
		return
	}
	provReq := llm.ToProviderRequest(p.parsed)
	resp, err := p.prov.Complete(ctx, provReq)
	if err != nil {
		if errors.Is(err, context.Canceled) {
			return
		}
		h.writeProviderFailure(p.w, p.r, err, requestID)
		return
	}
	defer func() {
		//nolint:errcheck // upstream body close after successful read; copy errors handled separately
		_ = resp.Body.Close()
	}()
	if p.parsed.Stream {
		forwardSSEStream(streamForwardParams{
			w:        p.w,
			r:        p.r,
			resp:     resp,
			provider: p.prov.Name(),
			metrics:  h.metrics,
			log:      h.log,
			docsBase: h.docsBase,
		})
		return
	}
	h.writeProviderSuccess(p.w, resp)
}

func (h chatCompletionHandler) writeProviderSuccess(w http.ResponseWriter, resp provider.Response) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	//nolint:errcheck // best-effort forward of upstream body; client disconnect is acceptable
	_, _ = io.Copy(w, resp.Body)
}

func (h chatCompletionHandler) writeProviderFailure(w http.ResponseWriter, r *http.Request, err error, requestID string) {
	mapped, write := provider.MapError(err)
	if !write || mapped == nil {
		return
	}
	logMappedProviderError(h, r, err, mapped)
	apierror.WriteHTTP(w, requestID, apierror.WriteOpts{DocsBase: h.docsBase}, mapped)
}

func logMappedProviderError(h chatCompletionHandler, r *http.Request, err error, mapped *apierror.Error) {
	if h.log == nil || mapped == nil {
		return
	}
	providerName := ""
	providerStatus := 0
	var pe *provider.ProviderError
	if errors.As(err, &pe) && pe != nil {
		providerName = pe.ProviderName
		providerStatus = pe.StatusCode
	}
	h.log.WarnCtx(r.Context(), "provider request failed",
		"provider", providerName,
		"provider_status", providerStatus,
		"ibex_code", string(mapped.Code),
	)
}
