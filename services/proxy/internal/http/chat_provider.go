package http

import (
	"context"
	"errors"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/injection"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type chatForwardParams struct {
	w      http.ResponseWriter
	r      *http.Request
	parsed *llm.ChatCompletionRequest
	prov   provider.Provider
}

type providerSuccessParams struct {
	w            http.ResponseWriter
	r            *http.Request
	parsed       *llm.ChatCompletionRequest
	providerName string
	resp         provider.Response
}

func (h chatCompletionHandler) forwardChatCompletion(p chatForwardParams) {
	p.r = h.resolveSessionForRequest(p.r, p.parsed, p.prov.Name())
	ctx := p.r.Context()
	requestID := requestIDFromContext(ctx)
	if errors.Is(ctx.Err(), context.Canceled) {
		return
	}
	provReq := llm.ToProviderRequest(p.parsed)
	provReq.Messages = applyDirectiveInjection(ctx, provReq.Messages)
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
			w: p.w, r: p.r, resp: resp, provider: p.prov.Name(),
			metrics: h.metrics, log: h.log, docsBase: h.docsBase,
			onComplete: h.streamCheckpointHook(p.r, p.parsed, p.prov.Name()),
		})
		return
	}
	h.writeProviderSuccess(providerSuccessParams{
		w: p.w, r: p.r, parsed: p.parsed, providerName: p.prov.Name(), resp: resp,
	})
}

// applyDirectiveInjection splices the resolved agent directive into messages.
// Missing context or empty content leaves messages unchanged (fail-open).
func applyDirectiveInjection(ctx context.Context, messages []provider.Message) []provider.Message {
	resolved, ok := ResolvedDirectiveFromContext(ctx)
	if !ok || !resolved.HasContent() {
		return messages
	}
	mode := injection.ParseMode(resolved.InjectionMode)
	return injection.Inject(messages, resolved.Content, mode)
}

func (h chatCompletionHandler) writeProviderSuccess(p providerSuccessParams) {
	body, err := readAllBody(p.resp.Body)
	if err != nil {
		h.writeProviderFailure(p.w, p.r, err, requestIDFromContext(p.r.Context()))
		return
	}
	setSessionResponseHeader(p.w, p.r.Context())
	p.w.Header().Set("Content-Type", "application/json")
	p.w.WriteHeader(p.resp.StatusCode)
	//nolint:errcheck // best-effort forward of upstream body; client disconnect is acceptable
	_, _ = p.w.Write(body)
	// Flush before Submit may block on a full non-dropping checkpoint queue.
	flushIfSupported(p.w)
	h.enqueueCheckpoint(p.r.Context(), checkpointInput{
		Messages: p.parsed.Messages, CompletionText: completionTextFromJSON(body),
		Model: p.parsed.Model, Provider: p.providerName, Usage: p.resp.Usage,
		Latency: p.resp.Latency, ProviderReqID: p.resp.ProviderRequestID,
		IsStreaming: false, IsComplete: true,
	})
}

func (h chatCompletionHandler) streamCheckpointHook(
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) func(streamCheckpointResult) {
	return func(res streamCheckpointResult) {
		h.enqueueCheckpoint(r.Context(), checkpointInput{
			Messages: parsed.Messages, CompletionText: res.content,
			Model: parsed.Model, Provider: providerName, Usage: res.usage,
			Latency: res.latency, IsStreaming: true, IsComplete: res.complete,
		})
	}
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
