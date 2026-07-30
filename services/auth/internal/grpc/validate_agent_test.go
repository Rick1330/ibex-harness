package grpcserver

import (
	"context"
	"testing"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestValidateAgent_MissingCallerContext(t *testing.T) {
	t.Parallel()

	s := &Server{
		metrics:      testAuthRegistry(),
		agentService: &fakeAgentAPI{},
	}

	_, err := s.ValidateAgent(context.Background(), &authv1.ValidateAgentRequest{
		AgentId: "00000000-0000-0000-0000-000000000000",
		OrgId:   "00000000-0000-0000-0000-000000000001",
	})
	if status.Code(err) != codes.Unauthenticated {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateAgent_ForbiddenOrgMismatch(t *testing.T) {
	t.Parallel()

	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   "00000000-0000-0000-0000-000000000001",
		TokenID: "t",
	})
	s := &Server{
		metrics: testAuthRegistry(),
		agentService: &fakeAgentAPI{
			view: service.AgentView{ID: "a", OrgID: "x", Status: "active"},
		},
	}

	_, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: "00000000-0000-0000-0000-000000000002",
		OrgId:   "00000000-0000-0000-0000-000000000003",
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateAgent_InvalidOrgId(t *testing.T) {
	t.Parallel()

	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   "not-a-uuid",
		TokenID: "t",
	})
	s := &Server{
		metrics:      testAuthRegistry(),
		agentService: &fakeAgentAPI{},
	}

	_, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: "00000000-0000-0000-0000-000000000002",
		OrgId:   "not-a-uuid",
	})
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateAgent_InvalidAgentId(t *testing.T) {
	t.Parallel()

	orgID := uuid.New().String()
	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   orgID,
		TokenID: "t",
	})
	s := &Server{
		metrics:      testAuthRegistry(),
		agentService: &fakeAgentAPI{},
	}

	_, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: "bad-agent-id",
		OrgId:   orgID,
	})
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateAgent_NotFoundBecomesPermissionDenied(t *testing.T) {
	t.Parallel()

	orgID := uuid.New().String()
	agentID := uuid.New().String()
	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   orgID,
		TokenID: "t",
	})

	s := &Server{
		metrics:      testAuthRegistry(),
		agentService: &fakeAgentAPI{},
	}

	_, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: agentID,
		OrgId:   orgID,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateAgent_InactiveAgentPermissionDenied(t *testing.T) {
	t.Parallel()

	orgID := uuid.New().String()
	agentID := uuid.New().String()
	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   orgID,
		TokenID: "t",
	})

	s := &Server{
		metrics: testAuthRegistry(),
		agentService: &fakeAgentAPI{
			err: service.ErrAgentInactive,
		},
	}

	_, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: agentID,
		OrgId:   orgID,
	})
	if status.Code(err) != codes.PermissionDenied {
		t.Fatalf("code: %v", status.Code(err))
	}
	if status.Convert(err).Message() != "agent is not active" {
		t.Fatalf("msg=%q want agent is not active", status.Convert(err).Message())
	}
}

func TestValidateAgent_StoreError(t *testing.T) {
	t.Parallel()

	orgID := uuid.New().String()
	agentID := uuid.New().String()
	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   orgID,
		TokenID: "t",
	})

	s := &Server{
		metrics: testAuthRegistry(),
		agentService: &fakeAgentAPI{
			err: service.ErrAgentLookup,
		},
	}

	_, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: agentID,
		OrgId:   orgID,
	})
	if status.Code(err) != codes.Internal {
		t.Fatalf("code: %v", status.Code(err))
	}
}

func TestValidateAgent_OK(t *testing.T) {
	t.Parallel()

	orgID := uuid.New().String()
	agentID := uuid.New().String()
	callerCtx := ContextWithCaller(context.Background(), CallerContext{
		OrgID:   orgID,
		TokenID: "t",
	})

	s := &Server{
		metrics: testAuthRegistry(),
		agentService: &fakeAgentAPI{
			view: service.AgentView{ID: agentID, OrgID: orgID, Status: "active"},
		},
	}

	resp, err := s.ValidateAgent(callerCtx, &authv1.ValidateAgentRequest{
		AgentId: agentID,
		OrgId:   orgID,
	})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if resp.GetAgentId() != agentID || resp.GetOrgId() != orgID || resp.GetStatus() != "active" {
		t.Fatalf("response mismatch: %+v", resp)
	}
}
