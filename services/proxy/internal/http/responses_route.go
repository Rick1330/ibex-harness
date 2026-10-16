package http

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/providercap"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

func ResponsesParseMiddleware(docsBase string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			body, err := io.ReadAll(r.Body)
			if err != nil {
				apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeInvalidJSON, "Malformed JSON in request body", requestIDFromContext(r.Context()), apierror.WriteOpts{DocsBase: docsBase})
				return
			}
			req, err := llm.ParseResponsesRequest(bytes.NewReader(body))
			if err != nil {
				apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeInvalidRequest, "Invalid Responses request", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: err.Error(), DocsBase: docsBase})
				return
			}
			ctx := llm.WithResponsesRequest(r.Context(), req)
			ctx = llm.WithChatRequest(ctx, &llm.ChatCompletionRequest{Model: req.Model, Stream: req.Stream})
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func ResponsesCapabilityMiddleware(manifest *providercap.Snapshot, docsBase string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			req, ok := llm.ResponsesRequestFromContext(r.Context())
			if !ok {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnknown)
				return
			}
			if req.Model == "" {
				if chatReq, ok := llm.ChatRequestFromContext(r.Context()); ok {
					req.Model = chatReq.Model
				}
			}
			prov, ok := provider.ProviderFromContext(r.Context())
			if !ok || manifest == nil {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnknown)
				return
			}
			if err := manifest.Require(prov.Name(), req.Model, "responses"); err != nil {
				writeResponsesCapabilityError(w, r.Context(), docsBase, err)
				return
			}
			if req.Stream {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnsupported)
				return
			}
			ctx := llm.WithResponsesRequest(r.Context(), req)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func writeResponsesCapabilityError(w http.ResponseWriter, ctx context.Context, docsBase string, err error) {
	code := apierror.CodeCapabilityUnknown
	status := http.StatusServiceUnavailable
	if errors.Is(err, providercap.ErrCapabilityUnsupported) {
		code = apierror.CodeCapabilityUnsupported
		status = http.StatusUnprocessableEntity
	}
	apierror.WriteStatus(w, status, code, "Responses capability unavailable", requestIDFromContext(ctx), apierror.WriteOpts{Detail: "requested Responses capability is not verified for this provider/model", DocsBase: docsBase})
}

func handleResponses(w http.ResponseWriter, r *http.Request) {
	req, ok := llm.ResponsesRequestFromContext(r.Context())
	if !ok {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError, "Internal error", requestIDFromContext(r.Context()), apierror.WriteOpts{})
		return
	}
	prov, ok := provider.ProviderFromContext(r.Context())
	if !ok {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError, "Internal error", requestIDFromContext(r.Context()), apierror.WriteOpts{})
		return
	}
	rp, ok := prov.(provider.ResponsesProvider)
	if !ok {
		writeResponsesCapabilityError(w, r.Context(), "", providercap.ErrCapabilityUnsupported)
		return
	}
	out, err := rp.CreateResponse(r.Context(), req)
	if err != nil {
		apierror.WriteStatus(w, http.StatusBadGateway, apierror.CodeProviderUnavailable, "Provider request failed", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "Responses provider request failed"})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(out.Raw)
}
