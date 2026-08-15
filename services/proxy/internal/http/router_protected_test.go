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
	"github.com/google/uuid"
)

func protectedAuthProbeRouter(t *testing.T, orgID uuid.UUID) http.Handler {
	t.Helper()
	validator := &mockValidator{res: &auth.ValidateResult{OrgID: orgID, Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	return newTestRouter(t, cfg, validator, ratelimit.Noop())
}

func serveAuthProbe(
	t *testing.T,
	handler http.Handler,
	method, path string,
	withAgent bool,
) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	if withAgent {
		req.Header.Set("X-IBEX-Agent-ID", agentTestAgentID())
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec
}

func TestProtectedRoutes_internalAuthProbe_success(t *testing.T) {
	t.Parallel()
	rec := serveAuthProbe(t, protectedAuthProbeRouter(t, agentTestOrgUUID), http.MethodGet, "/v1/internal/auth-probe", true)
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestProtectedRoutes_orgAuthProbe_success(t *testing.T) {
	t.Parallel()
	orgID := agentTestOrgID()
	rec := serveAuthProbe(
		t,
		protectedAuthProbeRouter(t, uuid.MustParse(orgID)),
		http.MethodGet,
		"/v1/orgs/"+orgID+"/auth-probe",
		true,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestProtectedRoutes_orgAuthProbe_orgMismatch(t *testing.T) {
	t.Parallel()
	otherOrg := "550e8400-e29b-41d4-a716-446655440099"
	rec := serveAuthProbe(
		t,
		protectedAuthProbeRouter(t, agentTestOrgUUID),
		http.MethodGet,
		"/v1/orgs/"+otherOrg+"/auth-probe",
		true,
	)
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
	rec := serveAuthProbe(
		t,
		protectedAuthProbeRouter(t, uuid.MustParse(orgID)),
		http.MethodPost,
		"/v1/orgs/"+orgID+"/auth-probe",
		false,
	)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestProtectedRoutes_internalAuthProbe_methodNotAllowed(t *testing.T) {
	t.Parallel()
	rec := serveAuthProbe(t, protectedAuthProbeRouter(t, agentTestOrgUUID), http.MethodPost, "/v1/internal/auth-probe", true)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeMethodNotAllowed)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
	if got := rec.Header().Get("Allow"); got != http.MethodGet {
		t.Fatalf("Allow: %q", got)
	}
}
