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
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

func runParseAgentIDCase(t *testing.T, tc parseAgentIDCase) {
	t.Helper()
	h := http.Header{}
	if tc.header != "" {
		h.Set(validation.HeaderAgentID, tc.header)
	}
	got := parseAgentIDHeader(h)
	if tc.wantNil {
		if got != uuid.Nil {
			t.Fatalf("got %v want Nil", got)
		}
		return
	}
	if got.String() != tc.wantID {
		t.Fatalf("got %s want %s", got, tc.wantID)
	}
}

func TestParseAgentIDHeader(t *testing.T) {
	t.Parallel()
	for _, tc := range parseAgentIDCases() {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			runParseAgentIDCase(t, tc)
		})
	}
}

func TestPathOrgUUIDMiddleware_invalidOrgID(t *testing.T) {
	t.Parallel()

	handler := chain(
		RequestContextMiddleware(config.Config{RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID"}),
		PathOrgUUIDMiddleware(""),
	)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/v1/orgs/not-a-uuid/auth-probe", nil)
	req.SetPathValue("org_id", "not-a-uuid")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeValidationError)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestPathOrgUUIDMiddleware_emptyOrgIDPassesThrough(t *testing.T) {
	t.Parallel()

	called := false
	handler := PathOrgUUIDMiddleware("")(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !called || rec.Code != http.StatusOK {
		t.Fatalf("called=%v status=%d", called, rec.Code)
	}
}

func TestHandleAuthProbe_missingAuthContext(t *testing.T) {
	t.Parallel()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req = req.WithContext(WithRequestID(req.Context(), "req-1"))
	handleAuthProbe(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), string(apierror.CodeServiceDegraded)) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestChain_skipsNilMiddleware(t *testing.T) {
	t.Parallel()

	called := false
	handler := chain(nil, nil)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	}))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if !called || rec.Code != http.StatusOK {
		t.Fatalf("called=%v status=%d", called, rec.Code)
	}
}

func TestProtectedRoutes_internalAuthProbe_missingAuthContext(t *testing.T) {
	t.Parallel()

	validator := &mockValidator{res: &auth.ValidateResult{OrgID: agentTestOrgID(), Permissions: permissions.Admin}}
	cfg := config.Config{
		Environment: "test", ServiceName: "proxy", Port: "8080",
		MaxRequestBodyBytes: 1 << 20, RequestIDHeader: "X-Request-ID", TraceIDHeader: "X-Trace-ID",
	}
	handler := newTestRouter(t, cfg, validator, ratelimit.Noop())

	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}
