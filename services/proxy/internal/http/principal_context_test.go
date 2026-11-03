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
	}, &auth.AgentRecord{ID: agent, OrgID: org, Status: "active"}, principalContextMetadata{
		requestID: "req-1", traceID: "trace-1", source: "proxy-auth", now: now,
	})
	if err != nil {
		t.Fatalf("mapper returned error: %v", err)
	}
	assertPrincipalIdentity(t, got, org, agent)
	assertPrincipalCorrelation(t, got)
	assertPrincipalTimestamps(t, got, now)
}

func assertPrincipalIdentity(t *testing.T, got *authv1.PrincipalContext, org, agent uuid.UUID) {
	t.Helper()
	if got.GetOrgId() != org.String() {
		t.Fatalf("org_id=%q want %q", got.GetOrgId(), org)
	}
	if got.GetAgentId() != agent.String() {
		t.Fatalf("agent_id=%q want %q", got.GetAgentId(), agent)
	}
	if got.GetPrincipalId() != "user-1" || got.GetPrincipalType() != "user" {
		t.Fatalf("principal identity: %v", got)
	}
}

func assertPrincipalCorrelation(t *testing.T, got *authv1.PrincipalContext) {
	t.Helper()
	if got.GetAuthority() != "AuthService" {
		t.Fatalf("authority=%q", got.GetAuthority())
	}
	if got.GetRequestId() != "req-1" || got.GetTraceId() != "trace-1" {
		t.Fatalf("correlation: request_id=%q trace_id=%q", got.GetRequestId(), got.GetTraceId())
	}
}

func assertPrincipalTimestamps(t *testing.T, got *authv1.PrincipalContext, now time.Time) {
	t.Helper()
	if !got.GetIssuedAt().AsTime().Equal(now) {
		t.Fatalf("issued_at=%v want %v", got.GetIssuedAt().AsTime(), now)
	}
	if !got.GetExpiresAt().AsTime().Equal(now.Add(time.Minute)) {
		t.Fatalf("expires_at=%v want %v", got.GetExpiresAt().AsTime(), now.Add(time.Minute))
	}
}

func TestPrincipalContextFromVerifiedAuthMapsServiceDefaults(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	got, err := principalContextFromVerifiedAuth(
		&auth.ValidateResult{OrgID: org},
		&auth.AgentRecord{ID: agent, OrgID: org}, principalContextMetadata{},
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
		&auth.AgentRecord{ID: verified, OrgID: org}, principalContextMetadata{now: time.Now()},
	)
	if !errors.Is(err, ErrPrincipalAgentMismatch) {
		t.Fatalf("error: got %v want %v", err, ErrPrincipalAgentMismatch)
	}
}

func TestPrincipalContextFromVerifiedAuthRejectsUnavailableBindings(t *testing.T) {
	t.Parallel()
	org, agent := uuid.New(), uuid.New()
	cases := []struct {
		name   string
		result *auth.ValidateResult
		record *auth.AgentRecord
	}{
		{name: "nil inputs"},
		{name: "nil record", result: &auth.ValidateResult{OrgID: org}},
		{name: "nil organization", result: &auth.ValidateResult{}, record: &auth.AgentRecord{ID: agent, OrgID: org}},
		{name: "missing agent id", result: &auth.ValidateResult{OrgID: org}, record: &auth.AgentRecord{OrgID: org}},
		{name: "missing agent organization", result: &auth.ValidateResult{OrgID: org}, record: &auth.AgentRecord{ID: agent}},
		{name: "cross organization", result: &auth.ValidateResult{OrgID: org}, record: &auth.AgentRecord{ID: agent, OrgID: uuid.New()}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := principalContextFromVerifiedAuth(tc.result, tc.record, principalContextMetadata{now: time.Now()}); !errors.Is(err, ErrPrincipalContextUnavailable) {
				t.Fatalf("error: got %v", err)
			}
		})
	}
}
