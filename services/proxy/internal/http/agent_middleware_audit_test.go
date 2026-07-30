package http

import (
	"bytes"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/validation"
)

func TestUnit_AgentVerification_AuditsAuthorizationDenied(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	log, err := logger.New(logger.Config{
		Service: "proxy", Level: slog.LevelWarn, Writer: &buf,
	})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}

	handler := AgentVerificationMiddleware(
		&mockAgentVerifier{err: auth.ErrAgentNotAuthorized}, log,
	)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("next handler must not run")
	}))

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/internal/auth-probe", nil)
	req.Header.Set("Authorization", "Bearer ibex_pat_test")
	req.Header.Set(validation.HeaderAgentID, agentTestAgentID())
	ctx := auth.WithContext(req.Context(), &auth.ValidateResult{OrgID: agentTestOrgUUID})
	ctx = reqid.WithRequestID(ctx, "req-agent-deny")
	req = req.WithContext(ctx)
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}

	logged := buf.String()
	assertAuditContains(t, logged, "agent authorization denied")
	assertAuditContains(t, logged, `"requesting_org_id":"`+agentTestOrgID()+`"`)
	assertAuditContains(t, logged, `"target_resource_type":"agent"`)
	assertAuditContains(t, logged, `"target_resource_id":"`+agentTestAgentID()+`"`)
	assertAuditContains(t, logged, "req-agent-deny")
}

func assertAuditContains(t *testing.T, logged, want string) {
	t.Helper()
	if !strings.Contains(logged, want) {
		t.Fatalf("audit log missing %q in %s", want, logged)
	}
}
