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

func TestProtectedRoutes_authProbe(t *testing.T) {
	t.Parallel()

	orgID := agentTestOrgID()
	otherOrg := "550e8400-e29b-41d4-a716-446655440099"

	cases := []authProbeCase{
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

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			validator := &mockValidator{res: &auth.ValidateResult{OrgID: tc.tokenOrg, Permissions: permissions.Admin}}
			cfg := config.Config{
				Environment: "test", ServiceName: "proxy", Port: "8080",
				MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
			}
			handler := newTestRouter(t, cfg, validator, ratelimit.Noop())

			req := httptest.NewRequest(tc.method, tc.path, nil)
			req.Header.Set("Authorization", "Bearer ibex_pat_test")
			if tc.withAgent {
				req.Header.Set("X-IBEX-Agent-ID", agentTestAgentID())
			}
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)

			if rec.Code != tc.wantStatus {
				t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
			}
			if tc.wantCode != "" && !strings.Contains(rec.Body.String(), tc.wantCode) {
				t.Fatalf("body: %s", rec.Body.String())
			}
			if tc.wantAllow != "" {
				if got := rec.Header().Get("Allow"); got != tc.wantAllow {
					t.Fatalf("Allow: %q", got)
				}
			}
		})
	}
}
