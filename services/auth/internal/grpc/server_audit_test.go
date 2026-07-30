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
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
)

func TestUnit_CreateToken_AuditsCrossTenant(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	s := newServerWithLog(t, &buf)
	callerOrg := uuid.NewString()
	targetOrg := uuid.NewString()
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: callerOrg, Permissions: permissions.Admin,
	})
	ctx = metadata.NewIncomingContext(ctx, metadata.Pairs(reqid.GRPCMetadataKey, "req-create-xt"))

	_, err := s.CreateToken(ctx, &authv1.CreateTokenRequest{OrgId: targetOrg, Name: "x"})
	assertGRPCCode(t, err, codes.PermissionDenied)

	logged := buf.String()
	assertLogContains(t, logged, "cross-tenant access attempt")
	assertLogContains(t, logged, `"requesting_org_id":"`+callerOrg+`"`)
	assertLogContains(t, logged, `"target_resource_type":"token"`)
	assertLogContains(t, logged, "req-create-xt")
}

func TestUnit_ValidateAgent_AuditsCrossTenantOnly(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	s := newServerWithLog(t, &buf)
	callerOrg := uuid.NewString()
	agentID := uuid.NewString()
	ctx := ContextWithCaller(context.Background(), CallerContext{
		OrgID: callerOrg, Permissions: permissions.Admin,
	})
	ctx = metadata.NewIncomingContext(ctx, metadata.Pairs(reqid.GRPCMetadataKey, "req-agent-xt"))

	_, err := s.ValidateAgent(ctx, &authv1.ValidateAgentRequest{
		OrgId: uuid.NewString(), AgentId: agentID,
	})
	assertGRPCCode(t, err, codes.PermissionDenied)

	logged := buf.String()
	assertLogContains(t, logged, "cross-tenant access attempt")
	assertLogContains(t, logged, `"requesting_org_id":"`+callerOrg+`"`)
	assertLogContains(t, logged, `"target_resource_type":"agent"`)
	assertLogContains(t, logged, `"target_resource_id":"`+agentID+`"`)
	assertLogContains(t, logged, "req-agent-xt")
}

func TestUnit_ValidateAgent_SameOrgMissDoesNotAuditCrossTenant(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	orgID := uuid.NewString()
	s := newServerWithLogAndAgents(t, &buf, &fakeAgentsStore{})
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

func newServerWithLog(t *testing.T, buf *bytes.Buffer) *Server {
	t.Helper()
	return newServerWithLogAndAgents(t, buf, &fakeAgentsStore{})
}

func newServerWithLogAndAgents(t *testing.T, buf *bytes.Buffer, agents AgentStore) *Server {
	t.Helper()
	log, err := logger.New(logger.Config{
		Service: "auth", Level: slog.LevelWarn, Writer: buf,
	})
	if err != nil {
		t.Fatalf("logger: %v", err)
	}
	tokenSvc := service.NewTokenService(&fakeTokenRepo{}, token.DefaultArgon2Params(), logger.Discard("auth"), nil)
	srv, err := NewServer(ServerDeps{
		Validator:    &fakeTokenValidator{},
		TokenService: tokenSvc,
		AgentsStore:  agents,
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
