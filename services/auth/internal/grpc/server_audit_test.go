package grpcserver

import (
	"bytes"
	"context"
	"log/slog"
	"strings"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
)

type auditCase struct {
	name         string
	resourceType string
	resourceID   string
	requestID    string
	invoke       func(context.Context, *Server) error
}

func TestUnit_AuditCrossTenant_NilLogNoop(t *testing.T) {
	t.Parallel()

	s := &Server{log: nil}
	s.auditCrossTenant(context.Background(), "org-a", "token", "id-1")
}

func TestUnit_WithIncomingRequestID(t *testing.T) {
	t.Parallel()

	base := context.Background()
	if withIncomingRequestID(base) != base {
		t.Fatal("expected same ctx without metadata")
	}

	empty := metadata.NewIncomingContext(base, metadata.Pairs(reqid.GRPCMetadataKey, ""))
	if withIncomingRequestID(empty) != empty {
		t.Fatal("expected same ctx for empty request id")
	}

	withID := metadata.NewIncomingContext(base, metadata.Pairs(reqid.GRPCMetadataKey, "rid-123"))
	got := withIncomingRequestID(withID)
	id, ok := reqid.FromContext(got)
	if !ok || id != "rid-123" {
		t.Fatalf("id=%q ok=%v", id, ok)
	}

	existing := reqid.WithRequestID(base, "ctx-rid")
	mdOverride := metadata.NewIncomingContext(existing, metadata.Pairs(reqid.GRPCMetadataKey, "md-rid"))
	got = withIncomingRequestID(mdOverride)
	id, ok = reqid.FromContext(got)
	if !ok || id != "ctx-rid" {
		t.Fatalf("existing request_id=%q ok=%v want ctx-rid preserved", id, ok)
	}
}

func TestUnit_AuditsCrossTenant(t *testing.T) {
	t.Parallel()

	callerOrg := uuid.NewString()
	targetOrg := uuid.NewString()
	agentID := uuid.NewString()
	for _, tc := range []auditCase{
		{
			name:         "create token",
			resourceType: "token",
			requestID:    "req-create-xt",
			invoke: func(ctx context.Context, s *Server) error {
				_, err := s.CreateToken(ctx, &authv1.CreateTokenRequest{OrgId: targetOrg, Name: "x"})
				return err
			},
		},
		{
			name:         "validate agent",
			resourceType: "agent",
			resourceID:   agentID,
			requestID:    "req-agent-xt",
			invoke: func(ctx context.Context, s *Server) error {
				_, err := s.ValidateAgent(ctx, &authv1.ValidateAgentRequest{
					OrgId: uuid.NewString(), AgentId: agentID,
				})
				return err
			},
		},
	} {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			assertCrossTenantAudit(t, callerOrg, tc)
		})
	}
}

func TestUnit_CreateToken_InvalidOrgDoesNotAuditCrossTenant(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	s := newServerWithLog(t, &buf)
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: uuid.NewString(), Permissions: permissions.Admin,
	})

	_, err := s.CreateToken(ctx, &authv1.CreateTokenRequest{OrgId: "bad-org-id", Name: "x"})
	assertGRPCCode(t, err, codes.InvalidArgument)

	if strings.Contains(buf.String(), "cross-tenant access attempt") {
		t.Fatalf("invalid org must not emit cross-tenant audit: %s", buf.String())
	}
}

func TestUnit_ValidateAgent_SameOrgMissDoesNotAuditCrossTenant(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	orgID := uuid.NewString()
	s := newServerWithLogAndAgents(t, &buf, &fakeAgentAPI{})
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: orgID, Permissions: permissions.Admin,
	})

	_, err := s.ValidateAgent(ctx, &authv1.ValidateAgentRequest{
		OrgId: orgID, AgentId: uuid.NewString(),
	})
	assertGRPCCode(t, err, codes.PermissionDenied)

	if strings.Contains(buf.String(), "cross-tenant access attempt") {
		t.Fatalf("same-org miss must not emit cross-tenant audit: %s", buf.String())
	}
}

func TestUnit_CreateToken_SubjectBindDeniedAudit(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	userID := uuid.NewString()
	tokens := &fakeTokenAPI{
		createFn: func(context.Context, service.CreateTokenInput) (service.CreateTokenResult, error) {
			return service.CreateTokenResult{}, service.ErrTokenSubjectForbidden
		},
	}
	s := newServerWithLogTokens(t, &buf, tokens)
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: orgID, Permissions: permissions.Admin,
	})
	ctx = metadata.NewIncomingContext(ctx, metadata.Pairs(reqid.GRPCMetadataKey, "req-bind"))

	_, err := s.CreateToken(ctx, &authv1.CreateTokenRequest{
		OrgId: orgID, Name: "bind", Permissions: permissions.AgentDefault,
		AgentId: &agentID, UserId: &userID,
	})
	assertGRPCCode(t, err, codes.PermissionDenied)

	logged := buf.String()
	if strings.Contains(logged, "cross-tenant access attempt") {
		t.Fatalf("bind deny must not use cross-tenant audit: %s", logged)
	}
	assertLogContains(t, logged, "token subject bind denied")
	assertLogContains(t, logged, `"target_resource_type":"token_bind"`)
	assertLogContains(t, logged, "agent:"+agentID+",user:"+userID)
	assertLogContains(t, logged, "req-bind")
}

func TestUnit_CreateToken_SubjectUnavailableNoBindAudit(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	orgID := uuid.NewString()
	agentID := uuid.NewString()
	tokens := &fakeTokenAPI{
		createFn: func(context.Context, service.CreateTokenInput) (service.CreateTokenResult, error) {
			return service.CreateTokenResult{}, service.ErrTokenSubjectUnavailable
		},
	}
	s := newServerWithLogTokens(t, &buf, tokens)
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: orgID, Permissions: permissions.Admin,
	})

	_, err := s.CreateToken(ctx, &authv1.CreateTokenRequest{
		OrgId: orgID, Name: "misconfig", Permissions: permissions.AgentDefault, AgentId: &agentID,
	})
	assertGRPCCode(t, err, codes.Internal)

	logged := buf.String()
	if strings.Contains(logged, "token subject bind denied") || strings.Contains(logged, "cross-tenant access attempt") {
		t.Fatalf("unavailable must not audit bind/cross-tenant: %s", logged)
	}
	assertLogContains(t, logged, "create token subject lookup unavailable")
}

func assertCrossTenantAudit(t *testing.T, callerOrg string, tc auditCase) {
	t.Helper()

	var buf bytes.Buffer
	s := newServerWithLog(t, &buf)
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: callerOrg, Permissions: permissions.Admin,
	})
	ctx = metadata.NewIncomingContext(ctx, metadata.Pairs(reqid.GRPCMetadataKey, tc.requestID))

	err := tc.invoke(ctx, s)
	assertGRPCCode(t, err, codes.PermissionDenied)

	logged := buf.String()
	assertLogContains(t, logged, "cross-tenant access attempt")
	assertLogContains(t, logged, `"requesting_org_id":"`+callerOrg+`"`)
	assertLogContains(t, logged, `"target_resource_type":"`+tc.resourceType+`"`)
	if tc.resourceID != "" {
		assertLogContains(t, logged, `"target_resource_id":"`+tc.resourceID+`"`)
	}
	assertLogContains(t, logged, tc.requestID)
}

func newServerWithLog(t *testing.T, buf *bytes.Buffer) *Server {
	t.Helper()
	return newServerWithDeps(t, buf, serverLogDeps{})
}

func newServerWithLogTokens(t *testing.T, buf *bytes.Buffer, tokens tokenAPI) *Server {
	t.Helper()
	return newServerWithDeps(t, buf, serverLogDeps{tokens: tokens})
}

func newServerWithLogAndAgents(t *testing.T, buf *bytes.Buffer, agents agentAPI) *Server {
	t.Helper()
	return newServerWithDeps(t, buf, serverLogDeps{agents: agents})
}

type serverLogDeps struct {
	tokens tokenAPI
	agents agentAPI
}

func newServerWithDeps(t *testing.T, buf *bytes.Buffer, d serverLogDeps) *Server {
	t.Helper()
	log, err := logger.New(logger.Config{
		Service: "auth", Level: slog.LevelWarn, Writer: buf,
	})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	tokens := tokenAPI(&fakeTokenAPI{})
	if d.tokens != nil {
		tokens = d.tokens
	}
	agents := agentAPI(&fakeAgentAPI{})
	if d.agents != nil {
		agents = d.agents
	}
	srv, err := NewServer(ServerDeps{
		Validator:    &fakeTokenValidator{},
		TokenService: tokens,
		AgentService: agents,
		Metrics:      testAuthRegistry(),
		Log:          log,
	})
	if err != nil {
		t.Fatalf("NewServer: %v", err)
	}
	return srv
}

func assertLogContains(t *testing.T, logged, want string) {
	t.Helper()
	if !strings.Contains(logged, want) {
		t.Fatalf("log missing %q in %s", want, logged)
	}
}
