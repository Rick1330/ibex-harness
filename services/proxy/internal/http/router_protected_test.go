package http

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestProtectedRoutes_internalAuthProbe_success(t *testing.T) {
	t.Parallel()

	validator := &mockValidator{res: &auth.ValidateResult{OrgID: agentTestOrgID(), Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	handler := newTestRouter(t, cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("X-IBEX-Agent-ID", agentTestAgentID())
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestProtectedRoutes_orgAuthProbe_success(t *testing.T) {
	t.Parallel()

	orgID := agentTestOrgID()
	validator := &mockValidator{res: &auth.ValidateResult{OrgID: orgID, Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	handler := newTestRouter(t, cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodGet, "/v1/orgs/"+orgID+"/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("X-IBEX-Agent-ID", agentTestAgentID())
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestProtectedRoutes_orgAuthProbe_orgMismatch(t *testing.T) {
	t.Parallel()

	validator := &mockValidator{res: &auth.ValidateResult{OrgID: agentTestOrgID(), Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	handler := newTestRouter(t, cfg, validator, ratelimit.Noop())

	otherOrg := "550e8400-e29b-41d4-a716-446655440099"
	req := httptest.NewRequest(http.MethodGet, "/v1/orgs/"+otherOrg+"/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set("X-IBEX-Agent-ID", agentTestAgentID())
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeInsufficientPermissions)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestProtectedRoutes_orgAuthProbe_methodNotAllowed(t *testing.T) {
	t.Parallel()

	orgID := agentTestOrgID()
	validator := &mockValidator{res: &auth.ValidateResult{OrgID: orgID, Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	handler := newTestRouter(t, cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodPost, "/v1/orgs/"+orgID+"/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}
