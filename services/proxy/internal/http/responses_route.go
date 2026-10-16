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
			req, prov, ok := responsesGateInputs(r, manifest)
			if !ok {
				writeResponsesCapabilityError(w, r.Context(), docsBase, providercap.ErrCapabilityUnknown)
				return
			}
			if err := checkResponsesCapability(manifest, prov.Name(), req); err != nil {
				writeResponsesCapabilityError(w, r.Context(), docsBase, err)
				return
			}
			next.ServeHTTP(w, r.WithContext(llm.WithResponsesRequest(r.Context(), req)))
		})
	}
}

func responsesGateInputs(r *http.Request, manifest *providercap.Snapshot) (providerresponses.Request, provider.Provider, bool) {
	req, ok := llm.ResponsesRequestFromContext(r.Context())
	if !ok {
		return providerresponses.Request{}, nil, false
	}
	req = withEffectiveResponsesModel(r, req)
	prov, ok := provider.ProviderFromContext(r.Context())
	if !ok || manifest == nil {
		return providerresponses.Request{}, nil, false
	}
	return req, prov, true
}

func withEffectiveResponsesModel(r *http.Request, req providerresponses.Request) providerresponses.Request {
	if req.Model != "" {
		return req
	}
	if chatReq, found := llm.ChatRequestFromContext(r.Context()); found {
		req.Model = chatReq.Model
	}
	return req
}

func checkResponsesCapability(manifest *providercap.Snapshot, providerName string, req providerresponses.Request) error {
	if err := manifest.Require(providerName, req.Model, req.RequiredCapabilities()...); err != nil {
		return err
	}
	if req.Stream {
		return providercap.ErrCapabilityUnsupported
	}
	return nil
}

func writeResponsesCapabilityError(w http.ResponseWriter, ctx context.Context, docsBase string, err error) {
	code, status := apierror.CodeCapabilityUnknown, http.StatusServiceUnavailable
	if errors.Is(err, providercap.ErrCapabilityUnsupported) {
		code, status = apierror.CodeCapabilityUnsupported, http.StatusUnprocessableEntity
	}
	apierror.WriteStatus(w, status, code, "Responses capability unavailable", requestIDFromContext(ctx), apierror.WriteOpts{Detail: "requested Responses capability is not verified for this provider/model", DocsBase: docsBase})
}

// responsesDispatch carries the validated request through to the provider call.
type responsesDispatch struct {
	req  providerresponses.Request
	rp   provider.ResponsesProvider
	cred providerresponses.CredentialOverride
}

// handleResponses performs the final tenant-safe dispatch and accounting transition.
func handleResponses(w http.ResponseWriter, r *http.Request, deps protectedRouteDeps) {
	dispatch, ok := requireResponsesDispatch(w, r, deps)
	if !ok {
		return
	}
	out, err := dispatch.rp.CreateResponse(r.Context(), dispatch.req, dispatch.cred)
	if err != nil {
		apierror.WriteStatus(w, http.StatusBadGateway, apierror.CodeProviderUnavailable, "Provider request failed", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "Responses provider request failed", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return
	}
	recordResponsesUsage(w, r, deps, responsesUsageInput{Provider: responsesProviderName(r), Model: dispatch.req.Model, Usage: out.Usage})
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(out.Raw)
}

func responsesProviderName(r *http.Request) string {
	prov, ok := provider.ProviderFromContext(r.Context())
	if !ok || prov == nil {
		return ""
	}
	return prov.Name()
}

func requireResponsesDispatch(w http.ResponseWriter, r *http.Request, deps protectedRouteDeps) (responsesDispatch, bool) {
	if !requireMethod(w, r, http.MethodPost, ErrorDocsBaseFromContext(r.Context())) {
		return responsesDispatch{}, false
	}
	req, ok := llm.ResponsesRequestFromContext(r.Context())
	if !ok {
		writeResponsesInternalError(w, r, "Responses request not parsed")
		return responsesDispatch{}, false
	}
	prov, ok := provider.ProviderFromContext(r.Context())
	if !ok {
		writeResponsesInternalError(w, r, "provider not selected")
		return responsesDispatch{}, false
	}
	rp, ok := prov.(provider.ResponsesProvider)
	if !ok {
		writeResponsesCapabilityError(w, r.Context(), ErrorDocsBaseFromContext(r.Context()), providercap.ErrCapabilityUnsupported)
		return responsesDispatch{}, false
	}
	if deps.credentialResolver == nil || deps.usageFactWriter == nil {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded, "Responses route unavailable", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "credential and usage dependencies are required", DocsBase: ErrorDocsBaseFromContext(r.Context())})
		return responsesDispatch{}, false
	}
	cred, ok := resolveResponsesCredential(w, r, deps.credentialResolver, prov.Name())
	if !ok {
		return responsesDispatch{}, false
	}
	return responsesDispatch{req: req, rp: rp, cred: cred}, true
}

func recordResponsesUsage(w http.ResponseWriter, r *http.Request, deps protectedRouteDeps, in responsesUsageInput) {
	if err := enqueueResponsesUsage(r.Context(), deps.usageFactWriter, in); err != nil {
		// The provider operation already succeeded. Returning a retryable error here
		// would cause clients to repeat a non-idempotent request. Preserve the
		// completed response and mark accounting for reconciliation instead.
		if deps.logger != nil {
			deps.logger.WarnCtx(r.Context(), "responses usage accounting pending",
				"request_id", requestIDFromContext(r.Context()),
				"provider", in.Provider,
				"model", in.Model,
				"error", err,
			)
		}
		w.Header().Set("X-IBEX-Usage-Accounting", "pending")
	}
}

func writeResponsesInternalError(w http.ResponseWriter, r *http.Request, detail string) {
	apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError, "Internal error", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: detail, DocsBase: ErrorDocsBaseFromContext(r.Context())})
}

func resolveResponsesCredential(w http.ResponseWriter, r *http.Request, resolver credentialResolver, providerName string) (providerresponses.CredentialOverride, bool) {
	docsBase := ErrorDocsBaseFromContext(r.Context())
	orgID, token, ok := responsesCredentialInputs(w, r, docsBase)
	if !ok {
		return providerresponses.CredentialOverride{}, false
	}
	result, err := resolver.Resolve(r.Context(), credentials.ResolveInput{OrgID: orgID, ProviderName: providerName, AccessToken: token})
	if err != nil {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeAuthUnavailable, "Auth service unavailable", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "provider key resolve failed", DocsBase: docsBase})
		return providerresponses.CredentialOverride{}, false
	}
	if result.PlatformDefault || strings.TrimSpace(result.BaseURL) == "" {
		return providerresponses.CredentialOverride{APIKey: result.APIKey}, true
	}
	return pinnedResponsesCredential(w, r, result, docsBase)
}

func responsesCredentialInputs(w http.ResponseWriter, r *http.Request, docsBase string) (string, string, bool) {
	authRes, authed := auth.FromContext(r.Context())
	if !authed || authRes.OrgID.String() == "" {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeAuthUnavailable, "Auth service unavailable", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "missing org context for key resolve", DocsBase: docsBase})
		return "", "", false
	}
	token, err := auth.ParseAuthorizationHeader(r.Header.Get("Authorization"))
	if err != nil || strings.TrimSpace(token) == "" {
		apierror.WriteStatus(w, http.StatusUnauthorized, apierror.CodeInvalidToken, "Invalid Authorization header", requestIDFromContext(r.Context()), apierror.WriteOpts{DocsBase: docsBase})
		return "", "", false
	}
	return authRes.OrgID.String(), token, true
}

func pinnedResponsesCredential(w http.ResponseWriter, r *http.Request, result credentials.Result, docsBase string) (providerresponses.CredentialOverride, bool) {
	pin, err := ssrf.ValidateAndPinHTTPURL(r.Context(), result.BaseURL)
	if err != nil {
		apierror.WriteStatus(w, http.StatusUnprocessableEntity, apierror.CodeInvalidCredential, "Invalid provider endpoint", requestIDFromContext(r.Context()), apierror.WriteOpts{Detail: "provider endpoint failed SSRF validation", DocsBase: docsBase})
		return providerresponses.CredentialOverride{}, false
	}
	return providerresponses.CredentialOverride{APIKey: result.APIKey, BaseURL: pin.PinnedURL, TLSServerName: pin.ServerName}, true
}

// responsesUsageInput bundles usage accounting fields so the writer stays testable.
type responsesUsageInput struct {
	Provider string
	Model    string
	Usage    *providerresponses.Usage
}

func enqueueResponsesUsage(ctx context.Context, writer *billing.UsageFactWriter, in responsesUsageInput) error {
	if err := validateResponsesUsage(in.Usage); err != nil {
		return err
	}
	org, agent, ok := tenantIDsFromContext(ctx)
	if !ok {
		return errors.New("tenant identity missing")
	}
	requestID := RequestIDFromContext(ctx)
	if requestID == "" {
		return errors.New("request identity missing")
	}
	return writer.Write(billing.UsageFact{RequestID: requestID, OrgID: org, AgentID: agent, Provider: in.Provider, Model: in.Model, InputTokens: uint32(in.Usage.InputTokens), OutputTokens: uint32(in.Usage.OutputTokens), TotalTokens: uint32(in.Usage.TotalTokens), RateCardVersion: "responses-v1", Completeness: "complete", OccurredAt: time.Now().UTC()})
}

func validateResponsesUsage(usage *providerresponses.Usage) error {
	if usage == nil {
		return errors.New("provider response did not include usage")
	}
	if usage.InputTokens > int(^uint32(0)) || usage.OutputTokens > int(^uint32(0)) {
		return errors.New("provider response usage exceeds billing limits")
	}
	return nil
}
