package http

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyerrors "github.com/Rick1330/ibex-harness/services/proxy/internal/errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/metrics"
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

func wrapAgentMiddleware(verifier auth.AgentVerifier) http.Handler {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rec, ok := AgentFromContext(r.Context())
		if !ok {
			http.Error(w, "no agent", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(rec.ID.String()))
	})
	return AgentVerificationMiddleware(verifier, metrics.New(), slog.New(slog.NewTextHandler(io.Discard, nil)))(inner)
}

func agentAuthedRequest(agentID string) *http.Request {
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	if agentID != "" {
		req.Header.Set(validation.HeaderAgentID, agentID)
	}
	ctx := auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: agentTestOrgID()})
	return req.WithContext(ctx)
}

func TestAgentVerification_Valid(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, agentAuthedRequest(agentTestAgentID()))
	if rec.Code != http.StatusOK {
		t.Fatalf("status: %d body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), agentTestAgentID()) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestAgentVerification_MissingHeader(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, agentAuthedRequest(""))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeMissingAgentID) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestAgentVerification_MalformedUUID(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, agentAuthedRequest("not-a-uuid"))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeValidationError) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestAgentVerification_WrongOrg(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{err: auth.ErrAgentNotAuthorized})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, agentAuthedRequest(agentTestAgentID()))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeAgentNotAuthorized) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestAgentVerification_AgentSuspended(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{err: auth.ErrAgentSuspended})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, agentAuthedRequest(agentTestAgentID()))
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeAgentSuspended) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestAgentVerification_AuthServiceDown(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{err: auth.ErrAgentVerifyUnavailable})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, agentAuthedRequest(agentTestAgentID()))
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status: %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), proxyerrors.CodeAuthUnavailable) {
		t.Fatalf("body: %s", rec.Body.String())
	}
}

func TestAgentVerification_NoAuthContext(t *testing.T) {
	handler := wrapAgentMiddleware(&mockAgentVerifier{})
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set(validation.HeaderAgentID, agentTestAgentID())
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status: %d", rec.Code)
	}
}
