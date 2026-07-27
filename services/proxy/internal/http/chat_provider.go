package http

import (
	"context"
	"errors"
	"net/http"
	"time"

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
	claim        *idempotencyClaim
}

type providerFailureParams struct {
	w            http.ResponseWriter
	r            *http.Request
	err          error
	requestID    string
	parsed       *llm.ChatCompletionRequest
	providerName string
	claim        *idempotencyClaim
}

func (h chatCompletionHandler) forwardChatCompletion(p chatForwardParams) {
	p.r = h.resolveSessionForRequest(p.r, p.parsed, p.prov.Name())
	claim, cont := h.resolveIdempotency(p.w, p.r, p.parsed)
	if !cont {
		return
	}
	if claim != nil && claim.replay {
		replayIdempotency(p.w, claim.hit)
		return
	}
	h.dispatchProviderCompletion(p, claim)
}

func (h chatCompletionHandler) dispatchProviderCompletion(p chatForwardParams, claim *idempotencyClaim) {
	ctx := p.r.Context()
	requestID := requestIDFromContext(ctx)
	if errors.Is(ctx.Err(), context.Canceled) {
		return
	}
	provReq := llm.ToProviderRequest(p.parsed)
	provReq.Messages = applyDirectiveInjection(ctx, provReq.Messages)
	start := time.Now()
	resp, err := p.prov.Complete(ctx, provReq)
	h.metrics.ObserveProviderDurationSeconds(p.prov.Name(), time.Since(start).Seconds())
	if err != nil {
		if errors.Is(err, context.Canceled) {
			return
		}
		h.writeProviderFailure(providerFailureParams{
			w: p.w, r: p.r, err: err, requestID: requestID,
			parsed: p.parsed, providerName: p.prov.Name(), claim: claim,
		})
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
		claim: claim,
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
		if errors.Is(err, errProviderResponseTooLarge) {
			err = &provider.ProviderError{
				ProviderName:   p.providerName,
				StatusCode:     http.StatusBadGateway,
				ProviderErrMsg: "provider response exceeds size limit",
			}
		}
		h.writeProviderFailure(providerFailureParams{
			w: p.w, r: p.r, err: err, requestID: requestIDFromContext(p.r.Context()),
			parsed: p.parsed, providerName: p.providerName, claim: p.claim,
		})
		return
	}
	setSessionResponseHeader(p.w, p.r.Context())
	p.w.Header().Set("Content-Type", "application/json")
	p.w.WriteHeader(p.resp.StatusCode)
	//nolint:errcheck // best-effort forward of upstream JSON body; client disconnect is acceptable
	writeJSONBody(p.w, body)
	// Flush before Submit may block on a full non-dropping checkpoint queue.
	flushIfSupported(p.w)
	h.finishIdempotency(p.claim, p.resp.StatusCode, body)
	h.enqueuePostResponse(p.r.Context(), checkpointInput{
		Messages: p.parsed.Messages, CompletionText: completionTextFromJSON(body),
		Model: p.parsed.Model, Provider: p.providerName, Usage: p.resp.Usage,
		Latency: p.resp.Latency, ProviderReqID: p.resp.ProviderRequestID,
		IsStreaming: false, IsComplete: true,
	}, requestOutcome{
		StatusCode: uint16(p.resp.StatusCode),
		IsComplete: true,
	})
}

func (h chatCompletionHandler) streamCheckpointHook(
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	providerName string,
) func(context.Context, streamCheckpointResult) {
	return func(ctx context.Context, res streamCheckpointResult) {
		status := uint16(http.StatusOK)
		errCode := ""
		if !res.complete {
			errCode = "STREAM_INCOMPLETE"
		}
		h.enqueuePostResponse(ctx, checkpointInput{
			Messages: parsed.Messages, CompletionText: res.content,
			Model: parsed.Model, Provider: providerName, Usage: res.usage,
			Latency: res.latency, IsStreaming: true, IsComplete: res.complete,
		}, requestOutcome{
			StatusCode: status,
			IsComplete: res.complete,
			ErrorCode:  errCode,
		})
	}
}

func (h chatCompletionHandler) writeProviderFailure(p providerFailureParams) {
	mapped, write := provider.MapError(p.err)
	if !write || mapped == nil {
		return
	}
	logMappedProviderError(h, p.r, p.err, mapped)
	cw := &capturingWriter{ResponseWriter: p.w, status: mapped.HTTPStatus}
	apierror.WriteHTTP(cw, p.requestID, apierror.WriteOpts{DocsBase: h.docsBase}, mapped)
	// Flush before Submit may block on a full non-dropping checkpoint queue.
	flushIfSupported(cw)
	h.finishIdempotency(p.claim, cw.status, cw.capturedBody())

	model, providerName := failureTraceIdentity(p)
	h.enqueuePostResponse(p.r.Context(), checkpointInput{
		Model: model, Provider: providerName,
		// Keep false so wantSessionCheckpoint skips empty failure checkpoints.
		IsStreaming: false, IsComplete: false,
	}, requestOutcome{
		StatusCode:      uint16(mapped.HTTPStatus),
		IsComplete:      false,
		ErrorCode:       string(mapped.Code),
		StreamRequested: failureStreamRequested(p),
	})
}

func failureStreamRequested(p providerFailureParams) bool {
	return p.parsed != nil && p.parsed.Stream
}

func failureTraceIdentity(p providerFailureParams) (model, providerName string) {
	if p.parsed != nil {
		model = p.parsed.Model
	}
	if p.providerName != "" {
		return model, p.providerName
	}
	var pe *provider.ProviderError
	if !errors.As(p.err, &pe) {
		return model, ""
	}
	if pe == nil {
		return model, ""
	}
	return model, pe.ProviderName
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
