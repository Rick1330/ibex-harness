package http

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	"github.com/google/uuid"
)

func mustNewRouter(tb testing.TB, deps RouterDeps) http.Handler {
	tb.Helper()
	// Unit tests historically assumed allow-all when ModelRouter was nil.
	// Production NewRouter defaults to DenyAllRegistry (4.P.1); tests opt into
	// the documented IBEX_MODEL_POLICY_ALLOW_PASSTHROUGH escape hatch unless
	// they set ModelRouter explicitly.
	if deps.ModelRouter == nil && deps.ProviderRegistry != nil {
		deps.ModelRouter = modelpolicy.PassthroughRegistry{Base: deps.ProviderRegistry}
	}
	h, err := NewRouter(deps)
	if err != nil {
		tb.Fatalf("NewRouter: %v", err)
	}
	return h
}

func TestUnit_NewRouter_NilModelRouterDeniesProtectedModel(t *testing.T) {
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
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeModelNotAllowed)) {
		t.Fatalf("body=%s", rec.Body.String())
	}
}
