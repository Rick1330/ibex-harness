package grpcserver

import (
	"context"
	"errors"
	"strings"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
	"github.com/Rick1330/ibex-harness/services/auth/internal/service"
	"github.com/Rick1330/ibex-harness/services/auth/internal/sessionjwt"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

const errMsgTOTPNotConfigured = "totp not configured"

type totpPort interface {
	BeginEnrollment(ctx context.Context, orgID, userID, accountName string) (string, error)
	ConfirmEnrollment(ctx context.Context, orgID, userID, code string) error
	CreateStepUp(ctx context.Context, orgID, userID, code string, permissions int64) (string, time.Time, error)
}

type sessionIssuerPort interface {
	IssuePair(sub, orgID string, permissions int64) (access, refresh string, accessExp, refreshExp time.Time, err error)
	RefreshPair(ctx context.Context, refreshToken string) (access, refresh string, accessExp, refreshExp time.Time, err error)
}

func (s *Server) BeginTotpEnrollment(
	ctx context.Context,
	req *authv1.BeginTotpEnrollmentRequest,
) (*authv1.BeginTotpEnrollmentResponse, error) {
	if s.totpService == nil {
		return nil, status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	}
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	orgID, userID := req.GetOrgId(), req.GetUserId()
	if caller.OrgID != orgID || caller.UserID == "" || caller.UserID != userID {
		return nil, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	uri, err := s.totpService.BeginEnrollment(ctx, orgID, userID, userID)
	if err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.BeginTotpEnrollmentResponse{OtpauthUri: uri}, nil
}

func (s *Server) ConfirmTotpEnrollment(
	ctx context.Context,
	req *authv1.ConfirmTotpEnrollmentRequest,
) (*authv1.ConfirmTotpEnrollmentResponse, error) {
	if s.totpService == nil {
		return nil, status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	}
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	orgID, userID := req.GetOrgId(), req.GetUserId()
	if caller.OrgID != orgID || caller.UserID == "" || caller.UserID != userID {
		return nil, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	if err := s.totpService.ConfirmEnrollment(ctx, orgID, userID, req.GetTotpCode()); err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.ConfirmTotpEnrollmentResponse{}, nil
}

func (s *Server) CreateStepUpToken(
	ctx context.Context,
	req *authv1.CreateStepUpTokenRequest,
) (*authv1.CreateStepUpTokenResponse, error) {
	if s.totpService == nil {
		return nil, status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	}
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	orgID, userID := req.GetOrgId(), req.GetUserId()
	if caller.OrgID != orgID || caller.UserID == "" || caller.UserID != userID {
		return nil, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	token, exp, err := s.totpService.CreateStepUp(ctx, orgID, userID, req.GetTotpCode(), caller.Permissions)
	if err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.CreateStepUpTokenResponse{
		StepUpToken: token,
		ExpiresAt:   timestamppb.New(exp),
	}, nil
}

func (s *Server) IssueOperatorSession(
	ctx context.Context,
	req *authv1.IssueOperatorSessionRequest,
) (*authv1.IssueOperatorSessionResponse, error) {
	if s.sessionIssuer == nil {
		return nil, status.Error(codes.FailedPrecondition, "session jwt issuer not configured")
	}
	if rt := strings.TrimSpace(req.GetRefreshToken()); rt != "" {
		return s.issueFromRefresh(ctx, rt)
	}
	return s.issueFromCaller(ctx)
}

func (s *Server) issueFromRefresh(ctx context.Context, refreshToken string) (*authv1.IssueOperatorSessionResponse, error) {
	access, refresh, accessExp, refreshExp, err := s.sessionIssuer.RefreshPair(ctx, refreshToken)
	if err != nil {
		return nil, mapRefreshPairErr(err)
	}
	return &authv1.IssueOperatorSessionResponse{
		AccessToken:      access,
		RefreshToken:     refresh,
		AccessExpiresAt:  timestamppb.New(accessExp),
		RefreshExpiresAt: timestamppb.New(refreshExp),
	}, nil
}

func mapRefreshPairErr(err error) error {
	if errors.Is(err, sessionjwt.ErrInvalidToken) || errors.Is(err, sessionjwt.ErrExpired) {
		return status.Error(codes.Unauthenticated, "invalid refresh token")
	}
	return status.Error(codes.Unavailable, "refresh unavailable")
}

func (s *Server) issueFromCaller(ctx context.Context) (*authv1.IssueOperatorSessionResponse, error) {
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return nil, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if caller.UserID == "" {
		return nil, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	access, refresh, accessExp, refreshExp, err := s.sessionIssuer.IssuePair(
		caller.UserID, caller.OrgID, caller.Permissions,
	)
	if err != nil {
		return nil, status.Error(codes.Internal, "issue session failed")
	}
	return &authv1.IssueOperatorSessionResponse{
		AccessToken:      access,
		RefreshToken:     refresh,
		AccessExpiresAt:  timestamppb.New(accessExp),
		RefreshExpiresAt: timestamppb.New(refreshExp),
	}, nil
}

func mapTotpErr(err error) error {
	switch {
	case errors.Is(err, service.ErrTOTPDisabled):
		return status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	case errors.Is(err, service.ErrTOTPNotReady), errors.Is(err, service.ErrSessionJWTMissing):
		return status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	case errors.Is(err, service.ErrTOTPInvalidCode):
		return status.Error(codes.Unauthenticated, "invalid totp code")
	case errors.Is(err, service.ErrTOTPLockedOut):
		return status.Error(codes.ResourceExhausted, "totp attempt limit exceeded")
	case errors.Is(err, service.ErrTOTPNotEnrolled):
		return status.Error(codes.FailedPrecondition, "totp not enrolled")
	case errors.Is(err, service.ErrTOTPAlreadyDone):
		return status.Error(codes.AlreadyExists, "totp already confirmed")
	case errors.Is(err, service.ErrInvalidArgument):
		return status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	default:
		return status.Error(codes.Internal, "totp operation failed")
	}
}

// Ensure sessionjwt.Issuer satisfies sessionIssuerPort.
var _ sessionIssuerPort = (*sessionjwt.Issuer)(nil)
