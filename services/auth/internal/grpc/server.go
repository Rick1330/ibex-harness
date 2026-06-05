package grpcserver

import (
	"context"
	"errors"
	"time"

	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/metrics"
	"github.com/Rick1330/ibex-harness/services/auth/internal/repository"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// Server implements ibex.auth.v1.AuthService.
type Server struct {
	authv1.UnimplementedAuthServiceServer
	validator    *token.Validator
	tokenService *service.TokenService
	metrics      *metrics.Metrics
	agentsStore  AgentStore
}

type AgentStore interface {
	GetByIDAndOrg(ctx context.Context, agentID, orgID uuid.UUID) (*repository.AgentRecord, error)
}

func NewServer(
	validator *token.Validator,
	tokenSvc *service.TokenService,
	agentsStore AgentStore,
	m *metrics.Metrics,
) *Server {
	return &Server{
		validator:    validator,
		tokenService: tokenSvc,
		metrics:      m,
		agentsStore:  agentsStore,
	}
}

func (s *Server) ValidateToken(ctx context.Context, req *authv1.ValidateTokenRequest) (*authv1.ValidateTokenResponse, error) {
	start := time.Now()
	resp, err := s.validator.Validate(ctx, req.GetAccessToken())
	elapsed := time.Since(start).Seconds()

	if err != nil {
		if errors.Is(err, token.ErrUnauthenticated) {
			s.metrics.ObserveValidateToken(elapsed, false)
			return nil, status.Error(codes.Unauthenticated, "invalid or expired token")
		}
		s.metrics.ObserveValidateToken(elapsed, false)
		return nil, status.Errorf(codes.Internal, "validation failed")
	}
	s.metrics.ObserveValidateToken(elapsed, true)
	return resp, nil
}

func (s *Server) CreateToken(ctx context.Context, req *authv1.CreateTokenRequest) (*authv1.CreateTokenResponse, error) {
	if err := RequireOrgAndPermission(ctx, req.GetOrgId(), permissions.TokenCreate); err != nil {
		return nil, err
	}
	result, err := s.tokenService.CreateToken(ctx, req)
	if err != nil {
		if errors.Is(err, service.ErrInvalidArgument) {
			return nil, status.Error(codes.InvalidArgument, "invalid request")
		}
		return nil, status.Errorf(codes.Internal, "create token failed")
	}
	s.metrics.IncTokenCreated()
	return &authv1.CreateTokenResponse{
		TokenId:   result.TokenID,
		Plaintext: result.Plaintext,
		Prefix:    result.Prefix,
		CreatedAt: timestamppb.New(result.CreatedAt),
	}, nil
}

func (s *Server) RevokeToken(ctx context.Context, req *authv1.RevokeTokenRequest) (*authv1.RevokeTokenResponse, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, "missing caller context")
	}
	if caller.OrgID != req.GetOrgId() {
		return nil, status.Error(codes.NotFound, "token not found")
	}
	if !CanRevoke(caller, req.GetOrgId(), req.GetTokenId()) {
		return nil, status.Error(codes.PermissionDenied, "forbidden")
	}
	var reason *string
	if req.RevokeReason != nil {
		reason = req.RevokeReason
	}
	// revoked_by references ibex_core.users (M1.1.7 FK); use caller user_id when present.
	err := s.tokenService.RevokeToken(ctx, req.GetOrgId(), req.GetTokenId(), caller.UserID, reason)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			return nil, status.Error(codes.NotFound, "token not found")
		}
		return nil, status.Errorf(codes.Internal, "revoke token failed")
	}
	s.metrics.IncTokenRevoked()
	return &authv1.RevokeTokenResponse{}, nil
}

func (s *Server) ListTokens(ctx context.Context, req *authv1.ListTokensRequest) (*authv1.ListTokensResponse, error) {
	if err := RequireOrgAndPermission(ctx, req.GetOrgId(), permissions.TokenCreate); err != nil {
		return nil, err
	}
	rows, next, err := s.tokenService.ListTokens(ctx, req.GetOrgId(), req.GetCursor(), req.GetLimit())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "list tokens failed")
	}
	s.metrics.IncListTokens()
	return &authv1.ListTokensResponse{
		Tokens:     service.ToProtoList(rows),
		NextCursor: next,
	}, nil
}

func (s *Server) ValidateAgent(ctx context.Context, req *authv1.ValidateAgentRequest) (*authv1.ValidateAgentResponse, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, "missing caller context")
	}

	// ValidateAgent is always tenant-scoped; never allow cross-org lookups.
	if caller.OrgID != req.GetOrgId() {
		return nil, status.Error(codes.PermissionDenied, "forbidden")
	}

	orgID, err := uuid.Parse(req.GetOrgId())
	if err != nil {
		return nil, status.Error(codes.InvalidArgument, "invalid org_id")
	}
	agentID, err := uuid.Parse(req.GetAgentId())
	if err != nil {
		return nil, status.Error(codes.InvalidArgument, "invalid agent_id")
	}

	rec, err := s.agentsStore.GetByIDAndOrg(ctx, agentID, orgID)
	if err != nil {
		return nil, status.Error(codes.Internal, "agent lookup failed")
	}
	if rec == nil {
		// Not found for this org is treated as permission denied to avoid existence leakage.
		return nil, status.Error(codes.PermissionDenied, "agent not found")
	}
	if rec.Status != "active" {
		return nil, status.Error(codes.PermissionDenied, "agent is not active")
	}

	return &authv1.ValidateAgentResponse{
		AgentId: rec.ID,
		OrgId:   rec.OrgID,
		Status:  rec.Status,
	}, nil
}
