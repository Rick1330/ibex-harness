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
	BeginEnrollment(ctx context.Context, p service.BeginEnrollmentParams) (string, error)
	ConfirmEnrollment(ctx context.Context, p service.ConfirmEnrollmentParams) error
	CreateStepUp(ctx context.Context, p service.CreateStepUpParams) (string, time.Time, error)
}

type sessionIssuerPort interface {
	IssuePair(sub, orgID string, permissions int64) (access, refresh string, accessExp, refreshExp time.Time, err error)
	RefreshPair(ctx context.Context, refreshToken string) (access, refresh string, accessExp, refreshExp time.Time, err error)
}

func (s *Server) requireTotpSelf(ctx context.Context, orgID, userID string) (CallerContext, error) {
	if s.totpService == nil {
		return CallerContext{}, status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	}
	caller, ok := CallerFromContext(ctx)
	if !ok {
		return CallerContext{}, status.Error(codes.Unauthenticated, errMsgMissingCallerContext)
	}
	if caller.OrgID != orgID {
		return CallerContext{}, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	if caller.UserID == "" || caller.UserID != userID {
		return CallerContext{}, status.Error(codes.PermissionDenied, errMsgForbidden)
	}
	return caller, nil
}

func (s *Server) BeginTotpEnrollment(
	ctx context.Context,
	req *authv1.BeginTotpEnrollmentRequest,
) (*authv1.BeginTotpEnrollmentResponse, error) {
	orgID, userID := req.GetOrgId(), req.GetUserId()
	if _, err := s.requireTotpSelf(ctx, orgID, userID); err != nil {
		return nil, err
	}
	uri, err := s.totpService.BeginEnrollment(ctx, service.BeginEnrollmentParams{
		OrgID: orgID, UserID: userID, AccountName: userID,
	})
	if err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.BeginTotpEnrollmentResponse{OtpauthUri: uri}, nil
}

func (s *Server) ConfirmTotpEnrollment(
	ctx context.Context,
	req *authv1.ConfirmTotpEnrollmentRequest,
) (*authv1.ConfirmTotpEnrollmentResponse, error) {
	orgID, userID := req.GetOrgId(), req.GetUserId()
	if _, err := s.requireTotpSelf(ctx, orgID, userID); err != nil {
		return nil, err
	}
	err := s.totpService.ConfirmEnrollment(ctx, service.ConfirmEnrollmentParams{
		OrgID: orgID, UserID: userID, Code: req.GetTotpCode(),
	})
	if err != nil {
		return nil, mapTotpErr(err)
	}
	return &authv1.ConfirmTotpEnrollmentResponse{}, nil
}

func (s *Server) CreateStepUpToken(
	ctx context.Context,
	req *authv1.CreateStepUpTokenRequest,
) (*authv1.CreateStepUpTokenResponse, error) {
	orgID, userID := req.GetOrgId(), req.GetUserId()
	caller, err := s.requireTotpSelf(ctx, orgID, userID)
	if err != nil {
		return nil, err
	}
	token, exp, err := s.totpService.CreateStepUp(ctx, service.CreateStepUpParams{
		OrgID: orgID, UserID: userID, Code: req.GetTotpCode(), Permissions: caller.Permissions,
	})
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
	if mapped := mapTotpClientErr(err); mapped != nil {
		return mapped
	}
	if mapped := mapTotpStateErr(err); mapped != nil {
		return mapped
	}
	return status.Error(codes.Internal, "totp operation failed")
}

func mapTotpClientErr(err error) error {
	switch {
	case errors.Is(err, service.ErrTOTPInvalidCode):
		return status.Error(codes.Unauthenticated, "invalid totp code")
	case errors.Is(err, service.ErrTOTPLockedOut):
		return status.Error(codes.ResourceExhausted, "totp attempt limit exceeded")
	case errors.Is(err, service.ErrTOTPUnavailable):
		return status.Error(codes.Unavailable, "totp attempt store unavailable")
	case errors.Is(err, service.ErrInvalidArgument):
		return status.Error(codes.InvalidArgument, errMsgInvalidRequest)
	default:
		return nil
	}
}

func mapTotpStateErr(err error) error {
	switch {
	case errors.Is(err, service.ErrTOTPDisabled),
		errors.Is(err, service.ErrTOTPNotReady),
		errors.Is(err, service.ErrSessionJWTMissing):
		return status.Error(codes.FailedPrecondition, errMsgTOTPNotConfigured)
	case errors.Is(err, service.ErrTOTPNotEnrolled):
		return status.Error(codes.FailedPrecondition, "totp not enrolled")
	case errors.Is(err, service.ErrTOTPAlreadyDone):
		return status.Error(codes.AlreadyExists, "totp already confirmed")
	default:
		return nil
	}
}

// Ensure sessionjwt.Issuer satisfies sessionIssuerPort.
var _ sessionIssuerPort = (*sessionjwt.Issuer)(nil)
