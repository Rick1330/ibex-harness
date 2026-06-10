package http

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"

	apierror "github.com/Rick1330/ibex-harness/packages/apierror"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
	"github.com/google/uuid"
)

type mockAgentVerifier struct {
	rec *auth.AgentRecord
	err error
}

func (m *mockAgentVerifier) Verify(_ context.Context, _, agentID, orgID string) (*auth.AgentRecord, error) {
	if m.err != nil {
		return nil, m.err
	}
	if m.rec != nil {
		return m.rec, nil
	}
	aid, _ := uuid.Parse(agentID)
	oid, _ := uuid.Parse(orgID)
	return &auth.AgentRecord{ID: aid, OrgID: oid, Status: "active"}, nil
}

func agentTestOrgID() string {
	return "550e8400-e29b-41d4-a716-446655440001"
}

func agentTestAgentID() string {
	return "550e8400-e29b-41d4-a716-446655440000"
}

func runAgentVerification(t *testing.T, verifier auth.AgentVerifier, agentID string, withAuth bool) *httptest.ResponseRecorder {
	t.Helper()
	handler := AgentVerificationMiddleware(verifier, logger.Discard("proxy"))(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			rec, ok := AgentFromContext(r.Context())
			if !ok {
				http.Error(w, "no agent", http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(rec.ID.String()))
		}),
	)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	if agentID != "" {
		req.Header.Set(validation.HeaderAgentID, agentID)
	}
	if withAuth {
		req = req.WithContext(auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: agentTestOrgID()}))
	}
	handler.ServeHTTP(rec, req)
	return rec
}

func TestAgentVerification(t *testing.T) {
	tests := []struct {
		name       string
		verifier   auth.AgentVerifier
		agentID    string
		withAuth   bool
		wantStatus int
		wantBody   string
	}{
		{name: "valid", verifier: &mockAgentVerifier{}, agentID: agentTestAgentID(), withAuth: true, wantStatus: http.StatusOK, wantBody: agentTestAgentID()},
		{name: "missing header", verifier: &mockAgentVerifier{}, agentID: "", withAuth: true, wantStatus: http.StatusBadRequest, wantBody: string(apierror.CodeMissingAgentID)},
		{name: "malformed uuid", verifier: &mockAgentVerifier{}, agentID: "not-a-uuid", withAuth: true, wantStatus: http.StatusBadRequest, wantBody: string(apierror.CodeValidationError)},
		{name: "wrong org", verifier: &mockAgentVerifier{err: auth.ErrAgentNotAuthorized}, agentID: agentTestAgentID(), withAuth: true, wantStatus: http.StatusForbidden, wantBody: string(apierror.CodeAgentNotAuthorized)},
		{name: "suspended", verifier: &mockAgentVerifier{err: auth.ErrAgentSuspended}, agentID: agentTestAgentID(), withAuth: true, wantStatus: http.StatusForbidden, wantBody: string(apierror.CodeAgentSuspended)},
		{name: "auth down", verifier: &mockAgentVerifier{err: auth.ErrAgentVerifyUnavailable}, agentID: agentTestAgentID(), withAuth: true, wantStatus: http.StatusServiceUnavailable, wantBody: string(apierror.CodeAuthUnavailable)},
		{name: "no auth context", verifier: &mockAgentVerifier{}, agentID: agentTestAgentID(), withAuth: false, wantStatus: http.StatusInternalServerError},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rec := runAgentVerification(t, tt.verifier, tt.agentID, tt.withAuth)
			if rec.Code != tt.wantStatus {
				t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
			}
			if tt.wantBody != "" && !strings.Contains(rec.Body.String(), tt.wantBody) {
				t.Fatalf("body: %s", rec.Body.String())
			}
		})
	}
}
