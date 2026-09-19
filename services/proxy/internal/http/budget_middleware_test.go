package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

type stubBudgetLoader struct {
	snap billing.BudgetSnapshot
	err  error
}

func (s stubBudgetLoader) LoadOrg(context.Context, uuid.UUID) (billing.BudgetSnapshot, error) {
	if s.err != nil {
		return billing.BudgetSnapshot{}, s.err
	}
	return s.snap, nil
}

func budgetTestHandler(t *testing.T, cache *billing.Cache) http.Handler {
	t.Helper()
	ok := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	return BudgetMiddleware(cache, logger.Discard("proxy"), metrics.NewProxy("test"))(ok)
}

func withAuthOrg(r *http.Request, orgID uuid.UUID) *http.Request {
	ctx := auth.WithContext(r.Context(), &auth.ValidateResult{OrgID: orgID})
	return r.WithContext(ctx)
}

func newBudgetCache(t *testing.T, loader billing.BudgetLoader) *billing.Cache {
	t.Helper()
	cache, err := billing.NewCache(loader, billing.Config{CacheTTL: time.Minute, LRUSize: 4}, billing.NoopMetrics{})
	if err != nil {
		t.Fatal(err)
	}
	return cache
}

func serveBudget(t *testing.T, cache *billing.Cache, orgID uuid.UUID) *httptest.ResponseRecorder {
	t.Helper()
	h := budgetTestHandler(t, cache)
	req := httptest.NewRequest(http.MethodGet, "/v1/chat/completions", nil)
	req = withAuthOrg(req, orgID)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

func TestBudgetMiddleware_nilCacheFailClosed402(t *testing.T) {
	t.Parallel()
	rr := serveBudget(t, nil, uuid.New())
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("code=%d", rr.Code)
	}
}

func TestBudgetMiddleware_exhaustedReturns402(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	cache := newBudgetCache(t, stubBudgetLoader{
		snap: billing.BudgetSnapshot{
			HasHardCap: true, CapCents: 10, SpentCents: 10, EnforcementMode: billing.EnforcementHardCap,
		},
	})
	rr := serveBudget(t, cache, org)
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("code=%d body=%s", rr.Code, rr.Body.String())
	}
	if got := rr.Body.String(); !containsCode(got, string(apierror.CodeBudgetExceeded)) {
		t.Fatalf("body=%s", got)
	}
}

func TestBudgetMiddleware_loaderErrorFailClosed402(t *testing.T) {
	t.Parallel()
	cache := newBudgetCache(t, stubBudgetLoader{err: errors.New("db down")})
	rr := serveBudget(t, cache, uuid.New())
	if rr.Code != http.StatusPaymentRequired {
		t.Fatalf("code=%d", rr.Code)
	}
}

func TestBudgetMiddleware_allowed(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	cache := newBudgetCache(t, stubBudgetLoader{
		snap: billing.BudgetSnapshot{
			HasHardCap: true, CapCents: 1000, SpentCents: 10, EnforcementMode: billing.EnforcementHardCap,
		},
	})
	rr := serveBudget(t, cache, org)
	if rr.Code != http.StatusOK {
		t.Fatalf("code=%d", rr.Code)
	}
}

func containsCode(body, code string) bool {
	return strings.Contains(body, code)
}

func TestBudgetMiddleware_missingAuthFailClosed(t *testing.T) {
	t.Parallel()
	cache := newBudgetCache(t, stubBudgetLoader{
		snap: billing.BudgetSnapshot{HasHardCap: true, CapCents: 100, SpentCents: 0, EnforcementMode: billing.EnforcementHardCap},
	})
	h := budgetTestHandler(t, cache)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status=%d", rec.Code)
	}
}

func TestBudgetMiddleware_nilOrgFailClosed(t *testing.T) {
	t.Parallel()
	cache := newBudgetCache(t, stubBudgetLoader{
		snap: billing.BudgetSnapshot{HasHardCap: true, CapCents: 100, SpentCents: 0, EnforcementMode: billing.EnforcementHardCap},
	})
	h := budgetTestHandler(t, cache)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: uuid.Nil}))
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status=%d", rec.Code)
	}
}
