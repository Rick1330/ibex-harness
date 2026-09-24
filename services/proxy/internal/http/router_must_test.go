package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/google/uuid"
)

func mustNewRouter(tb testing.TB, deps RouterDeps) http.Handler {
	tb.Helper()
	// Ordinary unit fixtures explicitly install this test-only resolver. The
	// production router's nil default remains fail-closed.
	if deps.ModelRouter == nil && deps.ProviderRegistry != nil {
		deps.ModelRouter = testAllowingModelResolver{base: deps.ProviderRegistry}
	}
	h, err := NewRouter(deps)
	if err != nil {
		tb.Fatalf("NewRouter: %v", err)
	}
	return h
}

type testAllowingModelResolver struct{ base *provider.Registry }

func (r testAllowingModelResolver) ForOrg(_ context.Context, _ uuid.UUID, model string) (provider.Provider, error) {
	return r.base.For(model)
}

func TestUnit_NewRouter_NilModelRouterReturnsPolicyUnavailable(t *testing.T) {
	t.Parallel()
	reg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog())
	if err != nil {
		t.Fatal(err)
	}
	org := uuid.MustParse("550e8400-e29b-41d4-a716-446655440099")
	deps := defaultChatRouterDeps(t)
	deps.ProviderRegistry = reg
	deps.ModelRouter = nil // exercise production DenyAll fallback directly
	deps.Config = config.Config{ServiceName: "proxy"}
	deps.Validator = &mockValidator{res: &auth.ValidateResult{
		OrgID: org, Permissions: permissions.ProxyChatCompletion,
	}}
	h, err := NewRouter(deps)
	if err != nil {
		t.Fatal(err)
	}
	body := `{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer tok")
	req.Header.Set("X-IBEX-Agent-ID", uuid.NewString())
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=%d body=%s", rec.Code, http.StatusServiceUnavailable, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeServiceDegraded)) {
		t.Fatalf("body=%s", rec.Body.String())
	}
}

func TestUnit_NewRouter_ProductionRequiresLimiterForProtectedRoutes(t *testing.T) {
	t.Parallel()
	deps := defaultChatRouterDeps(t)
	deps.Config.Environment = "production"
	deps.Limiter = nil
	if _, err := NewRouter(deps); err == nil {
		t.Fatal("NewRouter accepted production protected routes without a rate limiter")
	}
}
