package http

import (
	"context"
	"net/http"
	"time"

	"github.com/Rick1330/ibex-harness/packages/directive"
	"github.com/Rick1330/ibex-harness/packages/logger"
)

// ResolveTimeout budgets Redis GET plus a Postgres miss on the chat hot path.
// Cache SET after a miss uses a detached context so it is not starved by this deadline.
const ResolveTimeout = 100 * time.Millisecond

type directiveResolveHandler struct {
	resolver directive.Resolver
	logger   *logger.Logger
	next     http.Handler
}

// DirectiveResolveMiddleware resolves the agent directive after verification.
// On infrastructure failure (including timeout): fail open with a warning.
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
	start := time.Now()
	resolveCtx, cancel := context.WithTimeout(r.Context(), ResolveTimeout)
	defer cancel()
	resolved, err := h.resolver.Resolve(resolveCtx, agent.OrgID, agent.ID)
	elapsed := clampUint16Ms(time.Since(start))
	if err != nil {
		h.logger.WarnCtx(r.Context(), "directive resolve failed; continuing without directive",
			"org_id", agent.OrgID.String(),
			"agent_id", agent.ID.String(),
			"error", err,
		)
		ctx := WithDirectiveLatencyMs(r.Context(), elapsed)
		h.next.ServeHTTP(w, r.WithContext(ctx))
		return
	}
	ctx := WithResolvedDirective(r.Context(), resolved)
	ctx = WithDirectiveLatencyMs(ctx, elapsed)
	h.next.ServeHTTP(w, r.WithContext(ctx))
}
