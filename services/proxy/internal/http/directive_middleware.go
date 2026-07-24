package http

import (
	"net/http"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
)

type directiveResolveHandler struct {
	resolver directive.Resolver
	logger   *logger.Logger
	next     http.Handler
}

// DirectiveResolveMiddleware resolves the agent directive after verification.
// On infrastructure failure: fail open (continue without directive) with a warning.
// Does not mutate the LLM messages array (injection is milestone 2.3.3).
func DirectiveResolveMiddleware(
	resolver directive.Resolver,
	log *logger.Logger,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		if resolver == nil {
			resolver = directive.NoopResolver{}
		}
		return &directiveResolveHandler{resolver: resolver, logger: log, next: next}
	}
}

func (h *directiveResolveHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	agent, ok := AgentFromContext(r.Context())
	if !ok {
		h.next.ServeHTTP(w, r)
		return
	}
	resolved, err := h.resolver.Resolve(r.Context(), agent.OrgID, agent.ID)
	if err != nil {
		h.logger.WarnCtx(r.Context(), "directive resolve failed; continuing without directive",
			"org_id", agent.OrgID.String(),
			"agent_id", agent.ID.String(),
			"error", err,
		)
		h.next.ServeHTTP(w, r)
		return
	}
	ctx := WithResolvedDirective(r.Context(), resolved)
	h.next.ServeHTTP(w, r.WithContext(ctx))
}
