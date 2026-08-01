package grpcserver

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/permissions"
	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/packages/reqid"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/token"
	"github.com/google/uuid"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// tokenValidator validates bearer tokens for ValidateToken RPCs.
type tokenValidator interface {
	Validate(ctx context.Context, accessToken string) (*authv1.ValidateTokenResponse, error)
}

// tokenAPI is the service port used by token management RPCs.
type tokenAPI interface {
	CreateToken(ctx context.Context, in service.CreateTokenInput) (service.CreateTokenResult, error)
	RevokeToken(ctx context.Context, p service.RevokeTokenParams) error
	ListTokens(ctx context.Context, orgID, cursor string, limit int32) ([]service.TokenListItem, string, error)
}

// agentAPI is the service port used by ValidateAgent.
type agentAPI interface {
	ValidateForOrg(ctx context.Context, orgID, agentID uuid.UUID) (service.AgentView, error)
}

// ServerDeps groups AuthService construction dependencies.
// Validator, TokenService, AgentService, Metrics, and Log are required;
// NewServer rejects nil interfaces and typed-nil service pointers.
type ServerDeps struct {
	Validator    tokenValidator
	TokenService tokenAPI
	AgentService agentAPI
	Metrics      *metrics.AuthRegistry
	Log          *logger.Logger
}

// Server implements ibex.auth.v1.AuthService.
type Server struct {
	authv1.UnimplementedAuthServiceServer
	validator    tokenValidator
	tokenService tokenAPI
	metrics      *metrics.AuthRegistry
	agentService agentAPI
	log          *logger.Logger
}

var errInvalidOrgID = errors.New("invalid org_id")

// NewServer constructs an AuthService server.
// It fails when any required ServerDeps field is missing, including typed-nil
// TokenService or AgentService values stored in the interface fields.
func NewServer(deps ServerDeps) (*Server, error) {
	if isNilDep(deps.Validator) {
		return nil, fmt.Errorf("grpcserver: nil validator")
	}
	if isNilDep(deps.TokenService) {
		return nil, fmt.Errorf("grpcserver: nil tokenService")
	}
	if isNilDep(deps.AgentService) {
		return nil, fmt.Errorf("grpcserver: nil agentService")
	}
	if deps.Metrics == nil {
		return nil, fmt.Errorf("grpcserver: nil metrics registry")
	}
	if deps.Log == nil {
		return nil, fmt.Errorf("grpcserver: nil log")
	}
	return &Server{
		validator:    deps.Validator,
		tokenService: deps.TokenService,
		metrics:      deps.Metrics,
		agentService: deps.AgentService,
		log:          deps.Log,
	}, nil
}

// isNilDep reports whether v is a nil interface or holds a typed-nil value.
func isNilDep(v any) bool {
	if v == nil {
		return true
	}
	rv := reflect.ValueOf(v)
	switch rv.Kind() {
	case reflect.Chan, reflect.Func, reflect.Interface, reflect.Map, reflect.Ptr, reflect.Slice:
		return rv.IsNil()
	default:
		return false
	}
}

func (s *Server) ValidateToken(ctx context.Context, req *authv1.ValidateTokenRequest) (*authv1.ValidateTokenResponse, error) {
	start := time.Now()
	resp, err := s.validator.Validate(ctx, req.GetAccessToken())
	elapsed := time.Since(start).Seconds()

	if err != nil {
		if errors.Is(err, token.ErrUnauthenticated) {
			s.metrics.ObserveValidateToken(metrics.ValidateTokenObservation{
				Result: metrics.TokenResultError, Seconds: elapsed,
			})
			return nil, status.Error(codes.Unauthenticated, "invalid or expired token")
		}
		s.metrics.ObserveValidateToken(metrics.ValidateTokenObservation{
			Result: metrics.TokenResultError, Seconds: elapsed,
		})
		return nil, status.Errorf(codes.Internal, "validation failed")
	}
	s.metrics.ObserveValidateToken(metrics.ValidateTokenObservation{
		Result: metrics.TokenResultOK, Seconds: elapsed,
	})
	return resp, nil
}

func (s *Server) CreateToken(ctx context.Context, req *authv1.CreateTokenRequest) (*authv1.CreateTokenResponse, error) {
	in, err := s.authorizeCreateTokenRequest(ctx, req)
	if err != nil {
		return nil, err
	}
	result, err := s.tokenService.CreateToken(ctx, in)
	if err != nil {
		return nil, mapCreateTokenServiceErr(err)
	}
	return &authv1.CreateTokenResponse{
		TokenId:   result.TokenID,
		Plaintext: result.Plaintext,
		Prefix:    result.Prefix,
		CreatedAt: timestamppb.New(result.CreatedAt),
	}, nil
}

func mapCreateTokenServiceErr(err error) error {
	if errors.Is(err, service.ErrInvalidArgument) {
		return status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	}
	return status.Errorf(codes.Internal, "create token failed")
}

func (s *Server) authorizeCreateTokenRequest(ctx context.Context, req *authv1.CreateTokenRequest) (service.CreateTokenInput, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return service.CreateTokenInput{}, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	orgID, err := parseOrgID(req.GetOrgId())
	if err != nil {
		return service.CreateTokenInput{}, status.Error(codes.InvalidArgument, err.Error())
	}
	if caller.OrgID != orgID.String() {
		s.auditCrossTenant(ctx, caller.OrgID, "token", "")
		return service.CreateTokenInput{}, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	if err := RequireOrgAndPermission(ctx, req.GetOrgId(), permissions.TokenCreate); err != nil {
		return service.CreateTokenInput{}, err
	}
	if err := authorizeCreateTokenPermissions(caller.Permissions, req.GetPermissions()); err != nil {
		return service.CreateTokenInput{}, err
	}
	return createTokenInputFromProto(req)
}

// authorizeCreateTokenPermissions enforces requested ⊆ caller (no privilege
// escalation) and rejects reserved high bits on the requested bitmap.
func authorizeCreateTokenPermissions(callerPerms, requested int64) error {
	if permissions.UsesReservedHighBits(requested) {
		return status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	}
	if !permissions.Has(callerPerms, requested) {
		return status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	return nil
}

func createTokenInputFromProto(req *authv1.CreateTokenRequest) (service.CreateTokenInput, error) {
	in := service.CreateTokenInput{
		OrgID: req.GetOrgId(), Name: req.GetName(), Description: req.GetDescription(),
		Permissions: req.GetPermissions(), TokenType: service.TokenType(req.GetType()),
		UserID: req.UserId, AgentID: req.AgentId,
	}
	if ts := req.GetExpiresAt(); ts != nil {
		if err := ts.CheckValid(); err != nil {
			return service.CreateTokenInput{}, status.Error(codes.InvalidArgument, errMsgInvalidRequest)
		}
		t := ts.AsTime()
		in.ExpiresAt = &t
	}
	return in, nil
}

func (s *Server) RevokeToken(ctx context.Context, req *authv1.RevokeTokenRequest) (*authv1.RevokeTokenResponse, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if caller.OrgID != req.GetOrgId() {
		s.auditCrossTenant(ctx, caller.OrgID, "token", req.GetTokenId())
		return nil, status.Error(codes.PermissionDenied, "forbidden")
	}
	if !CanRevoke(caller, req.GetOrgId(), req.GetTokenId()) {
		return nil, status.Error(codes.PermissionDenied, "forbidden")
	}
	var reason *string
	if req.RevokeReason != nil {
		reason = req.RevokeReason
	}
	err := s.tokenService.RevokeToken(ctx, service.RevokeTokenParams{
		OrgID: req.GetOrgId(), TokenID: req.GetTokenId(), RevokedBy: caller.UserID, Reason: reason,
	})
	if err != nil {
		if errors.Is(err, service.ErrTokenNotFound) {
			return nil, status.Error(codes.NotFound, "token not found")
		}
		return nil, status.Errorf(codes.Internal, "revoke token failed")
	}
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
	return &authv1.ListTokensResponse{
		Tokens:     tokenListToProto(rows),
		NextCursor: next,
	}, nil
}

func (s *Server) ValidateAgent(ctx context.Context, req *authv1.ValidateAgentRequest) (*authv1.ValidateAgentResponse, error) {
	start := time.Now()

	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, s.agentValidateErr(start, metrics.AgentResultError, codes.Unauthenticated, errMsgMissingCallerContext)
	}

	orgID, agentID, err := parseValidateAgentIDs(req)
	if err != nil {
		return nil, s.agentValidateErr(start, metrics.AgentResultError, codes.InvalidArgument, err.Error())
	}
	if caller.OrgID != orgID.String() {
		s.auditCrossTenant(ctx, caller.OrgID, "agent", req.GetAgentId())
		return nil, s.agentValidateErr(start, metrics.AgentResultError, codes.PermissionDenied, "forbidden")
	}

	view, err := s.agentService.ValidateForOrg(ctx, orgID, agentID)
	if err != nil {
		return nil, s.mapValidateAgentErr(start, err)
	}

	s.observeValidateAgent(start, metrics.AgentResultOK)
	return &authv1.ValidateAgentResponse{
		AgentId: view.ID,
		OrgId:   view.OrgID,
		Status:  view.Status,
	}, nil
}

func (s *Server) auditCrossTenant(ctx context.Context, requestingOrg, resourceType, resourceID string) {
	if s.log == nil {
		return
	}
	ctx = withIncomingRequestID(ctx)
	s.log.WarnCtx(ctx, "cross-tenant access attempt",
		"requesting_org_id", requestingOrg,
		"target_resource_type", resourceType,
		"target_resource_id", resourceID,
	)
}

func withIncomingRequestID(ctx context.Context) context.Context {
	if _, ok := reqid.FromContext(ctx); ok {
		return ctx
	}
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return ctx
	}
	vals := md.Get(reqid.GRPCMetadataKey)
	if len(vals) != 1 || vals[0] == "" {
		return ctx
	}
	return reqid.WithRequestID(ctx, vals[0])
}

func parseValidateAgentIDs(req *authv1.ValidateAgentRequest) (uuid.UUID, uuid.UUID, error) {
	orgID, err := parseOrgID(req.GetOrgId())
	if err != nil {
		return uuid.Nil, uuid.Nil, err
	}
	agentID, err := uuid.Parse(req.GetAgentId())
	if err != nil {
		return uuid.Nil, uuid.Nil, errors.New("invalid agent_id")
	}
	return orgID, agentID, nil
}

func parseOrgID(raw string) (uuid.UUID, error) {
	orgID, err := uuid.Parse(raw)
	if err != nil {
		return uuid.Nil, errInvalidOrgID
	}
	return orgID, nil
}

func (s *Server) mapValidateAgentErr(start time.Time, err error) error {
	switch {
	case errors.Is(err, service.ErrAgentNotAuthorized):
		return s.agentValidateErr(start, metrics.AgentResultNotFound, codes.PermissionDenied, "agent not found")
	case errors.Is(err, service.ErrAgentInactive):
		// Metric label stays error (pre-MF-010). Message must be "agent is not active"
		// so proxy maps PermissionDenied → AGENT_SUSPENDED (ADR-0016).
		return s.agentValidateErr(start, metrics.AgentResultError, codes.PermissionDenied, "agent is not active")
	case errors.Is(err, context.Canceled):
		return s.agentValidateErr(start, metrics.AgentResultError, codes.Canceled, "request canceled")
	case errors.Is(err, context.DeadlineExceeded):
		return s.agentValidateErr(start, metrics.AgentResultError, codes.DeadlineExceeded, "deadline exceeded")
	default:
		return s.agentValidateErr(start, metrics.AgentResultError, codes.Internal, "agent lookup failed")
	}
}

func (s *Server) agentValidateErr(start time.Time, result metrics.AgentValidateResult, code codes.Code, msg string) error {
	s.observeValidateAgent(start, result)
	return status.Error(code, msg)
}

func (s *Server) observeValidateAgent(start time.Time, result metrics.AgentValidateResult) {
	s.metrics.ObserveValidateAgent(metrics.ValidateAgentObservation{
		Result:  result,
		Seconds: time.Since(start).Seconds(),
	})
}
