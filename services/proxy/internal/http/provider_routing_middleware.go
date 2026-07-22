package http

import (
	"errors"
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
)

type providerRoutingOpts struct {
	registry *provider.Registry
	log      *logger.Logger
	docsBase string
}

// ProviderRoutingMiddleware selects the LLM provider for the request model and
// attaches it to context. Required after ChatParseMiddleware.
func ProviderRoutingMiddleware(opts providerRoutingOpts) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			requestID := requestIDFromContext(r.Context())
			parsed, ok := llm.ChatRequestFromContext(r.Context())
			if !ok {
				opts.log.ErrorCtx(r.Context(), "chat request missing from context before provider routing")
				apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeInternalError,
					"Internal error", requestID,
					apierror.WriteOpts{Detail: "chat request not parsed", DocsBase: opts.docsBase})
				return
			}
			prov, err := opts.registry.For(parsed.Model)
			if err != nil {
				writeRegistryLookupError(w, requestID, opts.docsBase, parsed.Model, err)
				return
			}
			ctx := provider.WithProvider(r.Context(), prov)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func writeRegistryLookupError(w http.ResponseWriter, requestID, docsBase, model string, err error) {
	if errors.Is(err, provider.ErrNoProviderForModel) {
		writeProviderNotConfigured(w, requestID, docsBase, "No provider registered for model "+model)
		return
	}
	apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
		"Internal error", requestID,
		apierror.WriteOpts{Detail: "provider registry lookup failed", DocsBase: docsBase})
}
