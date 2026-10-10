package http

import (
	"errors"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
	"testing"
	"time"
)

func TestPrincipalContextFromVerifiedAuthMapsOnlyVerifiedIdentity(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	now := time.Date(2026, 10, 10, 14, 0, 0, 0, time.UTC)
	got, err := principalContextFromVerifiedAuth(&auth.ValidateResult{OrgID: org, AgentID: agent, UserID: "user-1", Permissions: 42, TokenID: "tok-1", ExpiresAt: now.Add(time.Minute)}, &auth.AgentRecord{ID: agent, OrgID: org, Status: "active"}, "req-1", "trace-1", "proxy-auth", now)
	if err != nil {
		t.Fatalf("mapper returned error: %v", err)
	}
	if got.GetOrgId() != org.String() || got.GetAgentId() != agent.String() || got.GetPrincipalId() != "user-1" || got.GetPrincipalType() != "user" {
		t.Fatalf("binding: %v", got)
	}
	if got.GetAuthority() != "AuthService" || got.GetRequestId() != "req-1" || got.GetTraceId() != "trace-1" {
		t.Fatalf("authority/correlation: %v", got)
	}
	if !got.GetIssuedAt().AsTime().Equal(now) || !got.GetExpiresAt().AsTime().Equal(now.Add(time.Minute)) {
		t.Fatalf("timestamps: %v", got)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsTokenAgentMismatch(t *testing.T) {
	t.Parallel()
	org, bound, verified := uuid.New(), uuid.New(), uuid.New()
	_, err := principalContextFromVerifiedAuth(&auth.ValidateResult{OrgID: org, AgentID: bound}, &auth.AgentRecord{ID: verified, OrgID: org, Status: "active"}, "", "", "", time.Now())
	if !errors.Is(err, ErrPrincipalAgentMismatch) {
		t.Fatalf("error: got %v want %v", err, ErrPrincipalAgentMismatch)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsMissingVerifierData(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	cases := []struct {
		name   string
		result *auth.ValidateResult
		record *auth.AgentRecord
	}{
		{name: "missing auth", record: &auth.AgentRecord{ID: agent, OrgID: org}},
		{name: "missing agent", result: &auth.ValidateResult{OrgID: org}},
		{name: "cross org", result: &auth.ValidateResult{OrgID: org}, record: &auth.AgentRecord{ID: agent, OrgID: uuid.New()}},
	}
	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if _, err := principalContextFromVerifiedAuth(tc.result, tc.record, "", "", "", time.Now()); !errors.Is(err, ErrPrincipalContextUnavailable) {
				t.Fatalf("error: got %v", err)
			}
		})
	}
}
