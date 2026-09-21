package http

import (
	"net/http"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

type budgetHandler struct {
	cache  *billing.Cache
	logger *logger.Logger
	reg    *metrics.ProxyRegistry
	next   http.Handler
}

// BudgetMiddleware enforces org spend hard-caps after rate limiting.
// On cache/loader failure: fail closed with BUDGET_EXCEEDED (HTTP 402).
// A nil cache also fails closed (callers must omit this middleware when budgets are disabled).
func BudgetMiddleware(cache *billing.Cache, log *logger.Logger, reg *metrics.ProxyRegistry) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return &budgetHandler{cache: cache, logger: log, reg: reg, next: next}
	}
}

func (h *budgetHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFromContext(r.Context())
	docsBase := ErrorDocsBaseFromContext(r.Context())
	if h.cache == nil {
		writeBudgetExceeded(w, requestID, docsBase, "Budget enforcement unavailable")
		return
	}

	res, ok := auth.FromContext(r.Context())
	if !ok {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestID,
			apierror.WriteOpts{Detail: "missing auth context", DocsBase: docsBase})
		return
	}
	orgID := res.OrgID
	if orgID == uuid.Nil {
		apierror.WriteStatus(w, http.StatusInternalServerError, apierror.CodeServiceDegraded,
			"Internal error", requestID,
			apierror.WriteOpts{Detail: "invalid org_id in auth context", DocsBase: docsBase})
		return
	}

	allowed, _, err := h.cache.Check(r.Context(), orgID)
	if err != nil {
		if h.logger != nil {
			h.logger.WarnCtx(r.Context(), "budget check failed; failing closed",
				"org_id", orgID.String(),
				"error", err,
			)
		}
		writeBudgetExceeded(w, requestID, docsBase, "Budget enforcement unavailable")
		return
	}
	if !allowed {
		writeBudgetExceeded(w, requestID, docsBase, "Organization spend hard-cap exceeded")
		return
	}
	h.next.ServeHTTP(w, r)
}

func writeBudgetExceeded(w http.ResponseWriter, requestID, docsBase, detail string) {
	apierror.WriteStatus(w, http.StatusPaymentRequired, apierror.CodeBudgetExceeded,
		"Budget exceeded for this organization", requestID,
		apierror.WriteOpts{Detail: detail, DocsBase: docsBase})
}
