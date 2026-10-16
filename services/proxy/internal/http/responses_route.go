package http

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/provider"
	providerresponses "github.com/Rick1330/ibex-harness/packages/provider/responses"
	"github.com/Rick1330/ibex-harness/packages/providercap"
	"github.com/Rick1330/ibex-harness/packages/ssrf"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/credentials"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

// ResponsesParseMiddleware parses the request once and carries it through routing.
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

// ResponsesCapabilityMiddleware rejects unsupported, stale, and unverified fields before dispatch.
func ResponsesCapabilityMiddleware(manifest *providercap.Snapshot, docsBase string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			req, ok := llm.ResponsesRequestFromContext(r.Context())
			if !ok {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnknown)
				return
			}
			if req.Model == "" {
				if chatReq, found := llm.ChatRequestFromContext(r.Context()); found {
					req.Model = chatReq.Model
				}
			}
			prov, ok := provider.ProviderFromContext(r.Context())
			if !ok || manifest == nil {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnknown)
				return
			}
			if err := manifest.Require(prov.Name(), req.Model, req.RequiredCapabilities()...); err != nil {
				writeResponsesCapabilityError(w, r.Context(), docsBase, err)
				return
			}
			if req.Stream {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnsupported)
				return
			}
			next.ServeHTTP(w, r.WithContext(llm.WithResponsesRequest(r.Context(), req)))
		})
	}
}

func writeResponsesCapabilityError(w http.ResponseWriter, ctx context.Context, docsBase string, err error) {
	code, status := apierror.CodeCapabilityUnknown, http.StatusServiceUnavailable
	if errors.Is(err, providercap.ErrCapabilityUnsupported) {
		code, status = apierror.CodeCapabilityUnsupported, http.StatusUnprocessableEntity
	}
	apierror.WriteStatus(w, status, code, "Responses capability unavailable", requestIDFromContext(ctx), apierror.WriteOpts{Detail: "requested Responses capability is not verified for this provider/model", DocsBase: docsBase})
}

// handleResponses performs the final tenant-safe dispatch and accounting transition.
func handleResponses(w http.ResponseWriter, r *http.Request, deps protectedRouteDeps) {
	if !requireMethod(w, r, http.MethodPost, ErrorDocsBaseFromContext(r.Context())) {
		return
	}
	req, ok := llm.ResponsesRequestFromContext(r.Context())
	if !ok {
		writeResponsesInternalError(w, r, "Responses request not parsed")
		return
	}
	prov, ok := provider.ProviderFromContext(r.Context())
	if !ok {
		writeResponsesInternalError(w, r, "provider not selected")
		return
	}
	rp, ok := prov.(provider.ResponsesProvider)
	if !ok {
		writeResponsesCapabilityError(w, r.Context(), ErrorDocsBaseFromContext(r.Context()), providercap.ErrCapabilityUnsupported)
		return
	}
	if deps.credentialResolver == nil || deps.usageFactWriter == nil {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded, "Responses route unavailable", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "credential and usage dependencies are required", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return
	}
	key, baseURL, tlsName, ok := resolveResponsesCredential(w, r, deps.credentialResolver, prov.Name(), ErrorDocsBaseFromContext(r.Context()))
	if !ok {
		return
	}
	out, err := rp.CreateResponse(r.Context(), req, key, baseURL, tlsName)
	if err != nil {
		apierror.WriteStatus(w, http.StatusBadGateway, apierror.CodeProviderUnavailable, "Provider request failed", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "Responses provider request failed", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return
	}
	if err := enqueueResponsesUsage(r.Context(), deps.usageFactWriter, prov.Name(), req.Model, out.Usage); err != nil {
		// The provider operation already succeeded. Returning a retryable error here
		// would cause clients to repeat a non-idempotent request. Preserve the
		// completed response and mark accounting for reconciliation instead.
		w.Header().Set("X-IBEX-Usage-Accounting", "pending")
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(out.Raw)
}

func writeResponsesInternalError(w http.ResponseWriter, r *http.Request, detail string) {
	apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError, "Internal error", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: detail, DocsBase: ErrorDocsBaseFromContext(r.Context())})
}

func resolveResponsesCredential(w http.ResponseWriter, r *http.Request, resolver credentialResolver, providerName, docsBase string) (string, string, string, bool) {
	authRes, authed := auth.FromContext(r.Context())
	if !authed || authRes.OrgID.String() == "" {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeAuthUnavailable, "Auth service unavailable", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "missing org context for key resolve", DocsBase: docsBase})
		return "", "", "", false
	}
	token, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
	if err != nil || strings.TrimSpace(token) == "" {
		apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken, "Invalid Authorization header", requestIDFromContext(r.Context()), apierror.WriteOpts{DocsBase: docsBase})
		return "", "", "", false
	}
	result, err := resolver.Resolve(r.Context(), credentials.ResolveInput{OrgID: authRes.OrgID.String(), ProviderName: providerName, AccessToken: token})
	if err != nil {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeAuthUnavailable, "Auth service unavailable", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "provider key resolve failed", DocsBase: docsBase})
		return "", "", "", false
	}
	if result.PlatformDefault || strings.TrimSpace(result.BaseURL) == "" {
		return result.APIKey, "", "", true
	}
	pin, err := ssrf.ValidateAndPinHTTPURL(r.Context(), result.BaseURL)
	if err != nil {
		apierror.WriteStatus(w, http.StatusUnprocessableEntity, apierror.CodeInvalidCredential, "Invalid provider endpoint", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "provider endpoint failed SSRF validation", DocsBase: docsBase})
		return "", "", "", false
	}
	return result.APIKey, pin.PinnedURL, pin.ServerName, true
}

func enqueueResponsesUsage(ctx context.Context, writer *billing.UsageFactWriter, providerName, model string, usage *providerresponses.Usage) error {
	if usage == nil {
		return errors.New("provider response did not include usage")
	}
	if usage.InputTokens > int(^uint32(0)) || usage.OutputTokens > int(^uint32(0)) {
		return errors.New("provider response usage exceeds billing limits")
	}
	org, agent, ok := tenantIDsFromContext(ctx)
	if !ok {
		return errors.New("tenant identity missing")
	}
	requestID := RequestIDFromContext(ctx)
	if requestID == "" {
		return errors.New("request identity missing")
	}
	return writer.Write(billing.UsageFact{RequestID: requestID, OrgID: org, AgentID: agent, Provider: providerName, Model: model, InputTokens: uint32(usage.InputTokens), OutputTokens: uint32(usage.OutputTokens), TotalTokens: uint32(usage.TotalTokens), RateCardVersion: "responses-v1", Completeness: "complete", OccurredAt: time.Now().UTC()})
}
