package http

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strconv"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

const msgProviderUnavailable = "Upstream LLM provider is unavailable"

type chatForwardParams struct {
	w      http.ResponseWriter
	r      *http.Request
	parsed *llm.ChatCompletionRequest
	prov   provider.Provider
}

func writeStreamingNotSupported(w http.ResponseWriter, requestID, docsBase string) {
	writeProviderNotConfigured(w, requestID, docsBase, "Streaming not supported until milestone 2.1.3")
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
		h.writeProviderFailure(p.w, err, requestID)
		return
	}
	defer func() {
		//nolint:errcheck // upstream body close after successful read; copy errors handled separately
		_ = resp.Body.Close()
	}()
	h.writeProviderSuccess(p.w, resp)
}

func (h chatCompletionHandler) writeProviderSuccess(w http.ResponseWriter, resp provider.Response) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	//nolint:errcheck // best-effort forward of upstream body; client disconnect is acceptable
	_, _ = io.Copy(w, resp.Body)
}

func (h chatCompletionHandler) writeProviderFailure(w http.ResponseWriter, err error, requestID string) {
	code, status, detail, retryAfter, ok := mapProviderErr(err)
	if !ok {
		return
	}
	opts := apierror.WriteOpts{Detail: detail, DocsBase: h.docsBase}
	if retryAfter > 0 {
		w.Header().Set("Retry-After", strconv.FormatInt(retryAfter, 10))
	}
	apierror.WriteStatus(w, status, code, providerClientMessage(code), requestID, opts)
}

func mapProviderErr(err error) (apierror.Code, int, string, int64, bool) {
	if errors.Is(err, context.Canceled) {
		return "", 0, "", 0, false
	}
	var pe *provider.ProviderError
	if errors.As(err, &pe) {
		code, status, detail, retry := mapProviderHTTPError(pe)
		return code, status, detail, retry, true
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return apierror.CodeProviderTimeout, apierror.HTTPStatus(apierror.CodeProviderTimeout),
			"Upstream LLM provider timed out", 0, true
	}
	return apierror.CodeProviderUnavailable, apierror.HTTPStatus(apierror.CodeProviderUnavailable),
		msgProviderUnavailable, 0, true
}

func mapProviderHTTPError(pe *provider.ProviderError) (apierror.Code, int, string, int64) {
	retrySecs := int64(pe.RetryAfter.Seconds())
	switch pe.StatusCode {
	case http.StatusBadRequest:
		return apierror.CodeInvalidRequest, http.StatusBadRequest, pe.ProviderErrMsg, 0
	case http.StatusTooManyRequests:
		return apierror.CodeRateLimited, http.StatusTooManyRequests, "Upstream LLM provider rate limited", retrySecs
	default:
		return apierror.CodeProviderUnavailable, apierror.HTTPStatus(apierror.CodeProviderUnavailable),
			msgProviderUnavailable, 0
	}
}

func providerClientMessage(code apierror.Code) string {
	switch code {
	case apierror.CodeInvalidRequest:
		return "Invalid request to LLM provider"
	case apierror.CodeRateLimited:
		return "Upstream LLM provider rate limited"
	case apierror.CodeProviderTimeout:
		return "Upstream LLM provider timed out"
	default:
		return msgProviderUnavailable
	}
}
