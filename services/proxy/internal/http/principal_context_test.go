package http

import (
	"errors"
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	"github.com/google/uuid"
)

func TestPrincipalContextFromVerifiedAuthMapsUserIdentity(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	now := time.Date(2026, 10, 10, 14, 0, 0, 0, time.UTC)
	got, err := principalContextFromVerifiedAuth(&auth.ValidateResult{
		OrgID: org, AgentID: agent, UserID: "user-1", Permissions: 42,
		TokenID: "tok-1", ExpiresAt: now.Add(time.Minute),
	}, &auth.AgentRecord{ID: agent, OrgID: org, Status: "active"}, "req-1", "trace-1", "proxy-auth", now)
	if err != nil {
		t.Fatalf("mapper returned error: %v", err)
	}
	assertPrincipalUserMapping(t, got, org, agent, now)
}

func assertPrincipalUserMapping(t *testing.T, got *authv1.PrincipalContext, org, agent uuid.UUID, now time.Time) {
	t.Helper()
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

func TestPrincipalContextFromVerifiedAuthMapsServiceDefaults(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	got, err := principalContextFromVerifiedAuth(
		&auth.ValidateResult{OrgID: org},
		&auth.AgentRecord{ID: agent, OrgID: org},
		"", "", "", time.Time{},
	)
	if err != nil {
		t.Fatalf("mapper returned error: %v", err)
	}
	if got.GetPrincipalId() != agent.String() || got.GetPrincipalType() != "service" {
		t.Fatalf("service identity: %v", got)
	}
	if got.GetSource() != "proxy-auth" || got.GetExpiresAt() != nil {
		t.Fatalf("defaults: %v", got)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsTokenAgentMismatch(t *testing.T) {
	t.Parallel()
	org, bound, verified := uuid.New(), uuid.New(), uuid.New()
	_, err := principalContextFromVerifiedAuth(
		&auth.ValidateResult{OrgID: org, AgentID: bound},
		&auth.AgentRecord{ID: verified, OrgID: org}, "", "", "", time.Now(),
	)
	if !errors.Is(err, ErrPrincipalAgentMismatch) {
		t.Fatalf("error: got %v want %v", err, ErrPrincipalAgentMismatch)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsNilInputs(t *testing.T) {
	t.Parallel()
	if _, err := principalContextFromVerifiedAuth(nil, nil, "", "", "", time.Now()); !errors.Is(err, ErrPrincipalContextUnavailable) {
		t.Fatalf("error: got %v", err)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsMissingAgentID(t *testing.T) {
	t.Parallel()
	org := uuid.New()
	_, err := principalContextFromVerifiedAuth(
		&auth.ValidateResult{OrgID: org},
		&auth.AgentRecord{OrgID: org}, "", "", "", time.Now(),
	)
	if !errors.Is(err, ErrPrincipalContextUnavailable) {
		t.Fatalf("error: got %v", err)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsCrossOrgAgent(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	_, err := principalContextFromVerifiedAuth(
		&auth.ValidateResult{OrgID: org},
		&auth.AgentRecord{ID: agent, OrgID: uuid.New()}, "", "", "", time.Now(),
	)
	if !errors.Is(err, ErrPrincipalContextUnavailable) {
		t.Fatalf("error: got %v", err)
	}
}
