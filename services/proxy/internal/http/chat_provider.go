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

func writeStreamingNotSupported(w http.ResponseWriter, requestID, docsBase string) {
	writeProviderNotConfigured(w, requestID, docsBase, "Streaming not supported until milestone 2.1.3")
}

func (h chatCompletionHandler) forwardChatCompletion(
	w http.ResponseWriter,
	r *http.Request,
	parsed *llm.ChatCompletionRequest,
	prov provider.Provider,
) {
	ctx := r.Context()
	requestID := requestIDFromContext(ctx)
	provReq := llm.ToProviderRequest(parsed)
	resp, err := prov.Complete(ctx, provReq)
	if err != nil {
		h.writeProviderFailure(w, err, requestID)
		return
	}
	defer func() { _ = resp.Body.Close() }()
	h.writeProviderSuccess(w, resp)
}

func (h chatCompletionHandler) writeProviderSuccess(w http.ResponseWriter, resp provider.Response) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func (h chatCompletionHandler) writeProviderFailure(w http.ResponseWriter, err error, requestID string) {
	code, status, detail, retryAfter := mapProviderErr(err)
	opts := apierror.WriteOpts{Detail: detail, DocsBase: h.docsBase}
	if retryAfter > 0 {
		w.Header().Set("Retry-After", strconv.FormatInt(retryAfter, 10))
	}
	apierror.WriteStatus(w, status, code, providerClientMessage(code), requestID, opts)
}

func mapProviderErr(err error) (apierror.Code, int, string, int64) {
	var pe *provider.ProviderError
	if errors.As(err, &pe) {
		return mapProviderHTTPError(pe)
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return apierror.CodeProviderTimeout, apierror.HTTPStatus(apierror.CodeProviderTimeout),
			"Upstream LLM provider timed out", 0
	}
	return apierror.CodeProviderUnavailable, apierror.HTTPStatus(apierror.CodeProviderUnavailable),
		msgProviderUnavailable, 0
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
