package http

import (
	"context"
	"errors"
	"net/http"
	"strings"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/google/uuid"
)

// ProviderResolver selects a provider for an org + model (ADR-0075).
type ProviderResolver interface {
	ForOrg(ctx context.Context, orgID uuid.UUID, model string) (provider.Provider, error)
}

type providerRoutingOpts struct {
	resolver      ProviderResolver
	agentDefaults modelpolicy.AgentDefaultLoader
	log           *logger.Logger
	docsBase      string
}

// ProviderRoutingMiddleware selects the LLM provider for the candidate model.
// Org identity comes from auth.FromContext (AuthMiddleware). Empty request model
// is filled from agents.default_model when AgentDefaults is configured.
// Deny → 403 MODEL_NOT_ALLOWED; unknown model → 501 PROVIDER_NOT_CONFIGURED.
func ProviderRoutingMiddleware(opts providerRoutingOpts) func(http.Handler) http.Handler {
	if opts.agentDefaults == nil {
		opts.agentDefaults = modelpolicy.NoopAgentDefaults{}
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			routeProviderRequest(w, r, opts, next)
		})
	}
}

func routeProviderRequest(w http.ResponseWriter, r *http.Request, opts providerRoutingOpts, next http.Handler) {
	requestID := requestIDFromContext(r.Context())
	parsed, ok := llm.ChatRequestFromContext(r.Context())
	if !ok {
		opts.log.ErrorCtx(r.Context(), "chat request missing from context before provider routing")
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "chat request not parsed", DocsBase: opts.docsBase})
		return
	}
	authRes, ok := auth.FromContext(r.Context())
	if !ok || authRes.OrgID == uuid.Nil {
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
			msgInternalError, requestID,
			apierror.WriteOpts{Detail: "missing org context", DocsBase: opts.docsBase})
		return
	}
	candidate, err := resolveRoutingModel(r.Context(), resolveModelArgs{
		requestModel: parsed.Model,
		orgID:        authRes.OrgID,
		loader:       opts.agentDefaults,
	})
	if !writeResolveModelError(w, requestID, opts.docsBase, err) {
		return
	}
	parsed.Model = candidate
	prov, err := opts.resolver.ForOrg(r.Context(), authRes.OrgID, candidate)
	if err != nil {
		writeRegistryLookupError(w, registryLookupWrite{
			requestID: requestID,
			docsBase:  opts.docsBase,
			model:     candidate,
		}, err)
		return
	}
	next.ServeHTTP(w, r.WithContext(provider.WithProvider(r.Context(), prov)))
}

// writeResolveModelError returns false when the request was already answered.
func writeResolveModelError(w http.ResponseWriter, requestID, docsBase string, err error) bool {
	if err == nil {
		return true
	}
	if errors.Is(err, errModelRequired) {
		writeModelRequired(w, requestID, docsBase)
		return false
	}
	apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
		msgInternalError, requestID,
		apierror.WriteOpts{Detail: "agent default model unavailable", DocsBase: docsBase})
	return false
}

type resolveModelArgs struct {
	requestModel string
	orgID        uuid.UUID
	loader       modelpolicy.AgentDefaultLoader
}

func resolveRoutingModel(ctx context.Context, args resolveModelArgs) (string, error) {
	if m := strings.TrimSpace(args.requestModel); m != "" {
		return m, nil
	}
	agent, ok := AgentFromContext(ctx)
	if !ok || agent.ID == uuid.Nil {
		return "", errModelRequired
	}
	// Defense in depth: never load defaults using a foreign agent.org_id.
	if agent.OrgID != args.orgID {
		return "", errModelRequired
	}
	defaults, err := args.loader.Load(ctx, args.orgID, agent.ID)
	if err != nil {
		return "", err
	}
	if m := modelpolicy.ResolveCandidateModel("", defaults); m != "" {
		return m, nil
	}
	return "", errModelRequired
}

var errModelRequired = errors.New("model is required")

func writeModelRequired(w http.ResponseWriter, requestID, docsBase string) {
	apierror.WriteStatus(w, http.StatusBadRequest, apierror.CodeValidationError,
		"Validation failed", requestID,
		apierror.WriteOpts{
			DocsBase: docsBase,
			FieldErrors: []apierror.FieldError{{
				Field: "model", Code: "REQUIRED", Message: "model is required",
			}},
		})
}

type registryLookupWrite struct {
	requestID string
	docsBase  string
	model     string
}

func writeRegistryLookupError(w http.ResponseWriter, meta registryLookupWrite, err error) {
	switch {
	case errors.Is(err, modelpolicy.ErrModelNotAllowedForOrg):
		apierror.WriteStatus(w, http.StatusForbidden, apierror.CodeModelNotAllowed,
			"Model not allowed for this organization", meta.requestID,
			apierror.WriteOpts{
				Detail:   "org model policy denies model " + meta.model,
				DocsBase: meta.docsBase,
			})
	case errors.Is(err, provider.ErrNoProviderForModel):
		writeProviderNotConfigured(w, meta.requestID, meta.docsBase,
			"No provider registered for model "+meta.model)
	case errors.Is(err, modelpolicy.ErrPolicyUnavailable):
		apierror.WriteStatus(w, http.StatusServiceUnavailable, apierror.CodeServiceDegraded,
			msgInternalError, meta.requestID,
			apierror.WriteOpts{Detail: "model policy unavailable", DocsBase: meta.docsBase})
	default:
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			msgInternalError, meta.requestID,
			apierror.WriteOpts{Detail: "provider registry lookup failed", DocsBase: meta.docsBase})
	}
}
