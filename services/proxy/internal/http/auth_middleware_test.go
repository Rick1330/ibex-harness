package http

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
)

type mockValidator struct {
	res *auth.ValidateResult
	err error
}

func (m *mockValidator) Validate(_ context.Context, _ string) (*auth.ValidateResult, error) {
	return m.res, m.err
}

func TestAuthMiddlewareMissingToken(t *testing.T) {
	handler := AuthMiddleware(&mockValidator{}, metrics.New(), logger.Discard("proxy"), AuthOptions{})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil))
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestAuthMiddlewareInvalidToken(t *testing.T) {
	handler := AuthMiddleware(&mockValidator{err: auth.ErrInvalidToken}, metrics.New(), logger.Discard("proxy"), AuthOptions{})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_bad")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestAuthMiddlewareAuthUnavailable(t *testing.T) {
	handler := AuthMiddleware(&mockValidator{err: auth.ErrAuthUnavailable}, metrics.New(), logger.Discard("proxy"), AuthOptions{})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_x")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestAuthMiddlewareInsufficientPermissions(t *testing.T) {
	handler := AuthMiddleware(&mockValidator{res: &auth.ValidateResult{OrgID: "org-a", Permissions: 0}}, metrics.New(), logger.Discard("proxy"), AuthOptions{RequireProxyChatCompletion: true})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_x")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestAuthMiddlewareOrgMismatch(t *testing.T) {
	handler := AuthMiddleware(&mockValidator{res: &auth.ValidateResult{OrgID: "org-a", Permissions: permissions.Admin}}, metrics.New(), logger.Discard("proxy"), AuthOptions{PathOrgID: "org-b"})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/orgs/org-b/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_x")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status: %d", rec.Code)
	}
}

func TestAuthMiddlewareSuccess(t *testing.T) {
	var gotOrg string
	handler := AuthMiddleware(&mockValidator{res: &auth.ValidateResult{OrgID: "org-a", Permissions: 42}}, metrics.New(), logger.Discard("proxy"), AuthOptions{})(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			res, ok := auth.FromContext(r.Context())
			if !ok {
				t.Fatal("missing auth context")
			}
			gotOrg = res.OrgID
			w.WriteHeader(http.StatusOK)
		}),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_x")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK || gotOrg != "org-a" {
		t.Fatalf("status=%d org=%s", rec.Code, gotOrg)
	}
}

func TestAuthMiddlewareUnexpectedError(t *testing.T) {
	handler := AuthMiddleware(&mockValidator{err: errors.New("boom")}, metrics.New(), logger.Discard("proxy"), AuthOptions{})(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_x")
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d", rec.Code)
	}
}
