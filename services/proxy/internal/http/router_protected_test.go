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

type authProbeCase struct {
	name       string
	tokenOrg   uuid.UUID
	method     string
	path       string
	withAgent  bool
	wantStatus int
	wantCode   string
	wantAllow  string
}

func authProbeCases() []authProbeCase {
	orgID := agentTestOrgID()
	otherOrg := "550e8400-e29b-41d4-a716-446655440099"
	return []authProbeCase{
		{
			name:       "internal_get_ok",
			tokenOrg:   agentTestOrgUUID,
			method:     http.MethodGet,
			path:       "/v1/internal/auth-probe",
			withAgent:  true,
			wantStatus: http.StatusOK,
		},
		{
			name:       "org_get_ok",
			tokenOrg:   uuid.MustParse(orgID),
			method:     http.MethodGet,
			path:       "/v1/orgs/" + orgID + "/auth-probe",
			withAgent:  true,
			wantStatus: http.StatusOK,
		},
		{
			name:       "org_mismatch_forbidden",
			tokenOrg:   agentTestOrgUUID,
			method:     http.MethodGet,
			path:       "/v1/orgs/" + otherOrg + "/auth-probe",
			withAgent:  true,
			wantStatus: http.StatusForbidden,
			wantCode:   string(apierror.CodeInsufficientPermissions),
		},
		{
			name:       "org_post_method_not_allowed",
			tokenOrg:   uuid.MustParse(orgID),
			method:     http.MethodPost,
			path:       "/v1/orgs/" + orgID + "/auth-probe",
			wantStatus: http.StatusMethodNotAllowed,
		},
		{
			name:       "internal_post_method_not_allowed",
			tokenOrg:   agentTestOrgUUID,
			method:     http.MethodPost,
			path:       "/v1/internal/auth-probe",
			withAgent:  true,
			wantStatus: http.StatusMethodNotAllowed,
			wantCode:   string(apierror.CodeMethodNotAllowed),
			wantAllow:  http.MethodGet,
		},
	}
}

func newAuthProbeHandler(t *testing.T, orgID uuid.UUID) http.Handler {
	t.Helper()
	validator := &mockValidator{res: &auth.ValidateResult{OrgID: orgID, Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	return newTestRouter(t, cfg, validator, ratelimit.Noop())
}

func newAuthProbeRequest(tc authProbeCase) *http.Request {
	req := httptest.NewRequest(tc.method, tc.path, nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	if !tc.withAgent {
		return req
	}
	req.Header.Set("X-IBEX-Agent-ID", agentTestAgentID())
	return req
}

func assertStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code == want {
		return
	}
	t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
}

func assertBodyContains(t *testing.T, rec *httptest.ResponseRecorder, want string) {
	t.Helper()
	if want == "" {
		return
	}
	if strings.Contains(rec.Body.String(), want) {
		return
	}
	t.Fatalf("body: %s", rec.Body.String())
}

func assertAllowHeader(t *testing.T, rec *httptest.ResponseRecorder, want string) {
	t.Helper()
	if want == "" {
		return
	}
	if got := rec.Header().Get("Allow"); got != want {
		t.Fatalf("Allow: %q", got)
	}
}

func TestProtectedRoutes_authProbe(t *testing.T) {
	t.Parallel()

	for _, tc := range authProbeCases() {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			rec := httptest.NewRecorder()
			newAuthProbeHandler(t, tc.tokenOrg).ServeHTTP(rec, newAuthProbeRequest(tc))
			assertStatus(t, rec, tc.wantStatus)
			assertBodyContains(t, rec, tc.wantCode)
			assertAllowHeader(t, rec, tc.wantAllow)
		})
	}
}
